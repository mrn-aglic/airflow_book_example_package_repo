# This entire file is the result of chapter09 since it introduces more movielens operators

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from airflow.models import BaseOperator
from airflow.providers.postgres.providers.hooks import PostgresHook

from ..hooks import MovielensHook


class MovielensFetchRatingsOperators(BaseOperator):
    """Operator that fetches ratings from the Movielens API.

    Parameters
    ----------
    conn_id : str
        ID of the connection to use to connect to the Movielens
        API. Connection is expected to include authentication
        details (login/password) and the host that is serving the API.
        output_path : str
        Path to write the fetched ratings to.
    start_date : str
        (Templated) start date to start fetching ratings from (inclusive).
        Expected format is YYYY-MM-DD (equal to Airflow"s ds formats).
    end_date : str
        (Templated) end date to fetching ratings up to (exclusive).
        Expected format is YYYY-MM-DD (equal to Airflow"s ds formats).

    """

    template_fields = ["_start_date", "_end_date", "_output_path"]

    def __init__(
        self,
        conn_id,
        output_path,
        start_date="{{ds}}",
        end_date="{{next_ds}}",
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._conn_id = conn_id
        self._output_path = output_path
        self._start_date = start_date
        self._end_date = end_date

    def execute(self, context: Any):
        hook = MovielensHook(self._conn_id)

        try:
            self.log.info(
                f"Fetching ratings for {self._start_date} to {self._end_date}"
            )

            ratings = list(
                hook.get_ratings(start_date=self._start_date, end_date=self._end_date)
            )

            self.log.info(f"Fetched {len(ratings)} ratings.")
        finally:
            hook.close()

        self.log.info(f"Writing ratings to {self._output_path}")

        path = self._output_path[: self._output_path.rfind("/")]
        Path(path).mkdir(parents=True, exist_ok=True)

        with open(self._output_path, "w") as file:
            json.dump(ratings, file)


# This operator is introduced in chapter 09 of the book Data Pipelines with Apache Airflow
class MovielensPopularityOperator(BaseOperator):
    def __init__(self, conn_id, start_date, end_date, min_ratings=4, top_n=5, **kwargs):
        super().__init__(**kwargs)
        self._conn_id = conn_id
        self._start_date = start_date
        self._end_date = end_date
        self._min_ratings = min_ratings
        self._top_n = top_n

    def execute(self, context: Any):
        with MovielensHook(self._conn_id) as hook:
            ratings = hook.get_ratings(
                start_date=self._start_date, end_date=self._end_date
            )

            rating_sums = defaultdict(Counter)
            for rating in ratings:
                rating_sums[rating["movieId"]].update(count=1, rating=rating["rating"])

            averages = {
                movie_id: (
                    rating_counter["rating"] / rating_counter["count"],
                    rating_counter["count"],
                )
                for movie_id, rating_counter in rating_sums.items()
                if rating_counter["count"] >= self._min_ratings
            }

            return sorted(averages.items(), key=lambda x: x[1], reverse=True)[
                : self._top_n
            ]


class MovielensDownloadOperator(BaseOperator):
    template_fields = ("_start_date", "_end_date", "_output_path")

    def __init__(
        self, conn_id: str, start_date: str, end_date: str, output_path: str, **kwargs
    ):
        super().__init__(**kwargs)

        self._conn_id = conn_id
        self._start_date = start_date
        self._end_date = end_date
        self._output_path = output_path

    def execute(self, context: Any):
        with MovielensHook(self._conn_id) as hook:
            ratings = hook.get_ratings(
                start_date=self._start_date, end_date=self._end_date
            )

        with open(self._output_path, "w") as file:
            json.dump(list(ratings), file, sort_keys=True, indent=4, ensure_ascii=False)


class MovielensToPostgresOperator(BaseOperator):
    template_fields = ("_start_date", "_end_date", "_insert_query")

    def __init__(
        self,
        movielens_conn_id: str,
        start_date: str,
        end_date: str,
        postgres_conn_id: str,
        insert_query: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._movielens_conn_id = movielens_conn_id
        self._start_date = start_date
        self._end_date = end_date
        self._postgres_conn_id = postgres_conn_id
        self._insert_query = insert_query

    def execute(self, context: Any):
        with MovielensHook(self._movielens_conn_id) as movie_hook:
            ratings = list(movie_hook.get_ratings(self._start_date, self._end_date))

            postgres_hook = PostgresHook(postgres_conn_id=self._postgres_conn_id)

            insert_queries = [
                self._insert_query.format(
                    ",".join([str(_[1]) for _ in sorted(rating.items())])
                )
                for rating in ratings
            ]

            postgres_hook.run(insert_queries)
