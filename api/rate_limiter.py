"""Rate limiting utility functions for QueryWeaver."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status

from api.extensions import db


class RateLimiter:
    """Rate limiting functionality for query endpoints."""

    def __init__(self, daily_limit: Optional[int] = None):
        # Get rate limit from environment variable or use default
        self.daily_limit = daily_limit or int(os.getenv("DAILY_QUERY_LIMIT", "100"))
        logging.info("Rate limiting configured: %d queries per user per day", self.daily_limit)

    async def check_and_increment_rate_limit(self, user_id: str) -> None:
        """
        Check if user has exceeded their daily query limit and increment count.
        Raises HTTPException if limit is exceeded.
        """
        if not await self._check_rate_limit(user_id):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(f"Daily query limit exceeded. "
                       f"You can make {self.daily_limit} queries per day."),
                headers={
                    "X-RateLimit-Limit": str(self.daily_limit),
                    "X-RateLimit-Reset": "UTC midnight"
                }
            )

        # Increment query count after successful rate limit check
        await self._increment_query_count(user_id)

    async def _check_rate_limit(self, user_id: str) -> bool:
        """Check if user has exceeded their daily query limit."""
        try:
            organizations_graph = db.select_graph("Organizations")
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Query to check current query count for today
            # Fixed relationship direction: Identity -[:AUTHENTICATES]-> User
            query = """
            MATCH (identity:Identity {provider_user_id: $user_id})-[:AUTHENTICATES]->(user:User)
            OPTIONAL MATCH (user)-[:HAS_QUERY_COUNT]->(qc:QueryCount {date: $today})
            RETURN COALESCE(qc.count, 0) as query_count
            """

            result = organizations_graph.query(query, {
                "user_id": user_id,
                "today": today
            })

            if result.result_set:
                current_count = result.result_set[0][0]
                return current_count < self.daily_limit

            # If no result, user hasn't made any queries today, so they're under the limit
            return True

        except Exception as exc:
            logging.error("Error checking rate limit for user %s: %s", user_id, exc)
            # In case of database error, allow the request to proceed
            return True

    async def _increment_query_count(self, user_id: str) -> None:
        """Increment the query count for the user for today."""
        try:
            organizations_graph = db.select_graph("Organizations")
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Query to increment query count, creating the count node if it doesn't exist
            # Fixed relationship direction: Identity -[:AUTHENTICATES]-> User
            query = """
            MATCH (identity:Identity {provider_user_id: $user_id})-[:AUTHENTICATES]->(user:User)
            MERGE (user)-[:HAS_QUERY_COUNT]->(qc:QueryCount {date: $today})
            ON CREATE SET qc.count = 1, qc.created_at = timestamp()
            ON MATCH SET qc.count = qc.count + 1, qc.updated_at = timestamp()
            RETURN qc.count as new_count
            """

            result = organizations_graph.query(query, {
                "user_id": user_id,
                "today": today
            })

            if result.result_set:
                new_count = result.result_set[0][0]
                logging.info("User %s query count for %s: %d/%d",
                           user_id, today, new_count, self.daily_limit)

        except Exception as exc:
            logging.error("Error incrementing query count for user %s: %s", user_id, exc)
            # Don't fail the request if we can't update the count


# Global rate limiter instance
rate_limiter = RateLimiter()