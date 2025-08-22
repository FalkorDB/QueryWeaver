"""Tests for rate limiting functionality."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from api.rate_limiter import RateLimiter
from fastapi import HTTPException, status


@pytest.fixture
def rate_limiter():
    """Create a rate limiter instance for testing."""
    return RateLimiter(daily_limit=5)  # Small limit for testing


@pytest.fixture
def mock_db():
    """Mock database connection."""
    with patch('api.rate_limiter.db') as mock_db:
        mock_graph = Mock()
        mock_db.select_graph.return_value = mock_graph
        yield mock_graph


class TestRateLimiter:
    """Test cases for rate limiting functionality."""

    def test_rate_limiter_initialization_default_limit(self):
        """Test rate limiter initializes with default limit from environment."""
        with patch.dict('os.environ', {'DAILY_QUERY_LIMIT': '50'}):
            limiter = RateLimiter()
            assert limiter.daily_limit == 50

    def test_rate_limiter_initialization_explicit_limit(self):
        """Test rate limiter initializes with explicit limit."""
        limiter = RateLimiter(daily_limit=25)
        assert limiter.daily_limit == 25

    def test_rate_limiter_initialization_fallback_default(self):
        """Test rate limiter uses fallback default when env var not set."""
        with patch.dict('os.environ', {}, clear=True):
            limiter = RateLimiter()
            assert limiter.daily_limit == 100

    @pytest.mark.asyncio
    async def test_check_rate_limit_under_limit(self, rate_limiter, mock_db):
        """Test rate limit check when user is under the limit."""
        # Mock database response - user has made 3 queries today (under limit of 5)
        mock_result = Mock()
        mock_result.result_set = [[3]]  # Current count
        mock_db.query.return_value = mock_result

        result = await rate_limiter._check_rate_limit("test_user_123")
        assert result is True

        # Verify correct query was called
        mock_db.query.assert_called_once()
        call_args = mock_db.query.call_args
        query_str = call_args[0][0]  # First positional argument
        params = call_args[0][1]     # Second positional argument
        
        assert "provider_user_id: $user_id" in query_str
        assert params["user_id"] == "test_user_123"
        assert "today" in params

    @pytest.mark.asyncio
    async def test_check_rate_limit_at_limit(self, rate_limiter, mock_db):
        """Test rate limit check when user is at the limit."""
        # Mock database response - user has made 5 queries today (at limit)
        mock_result = Mock()
        mock_result.result_set = [[5]]  # Current count
        mock_db.query.return_value = mock_result

        result = await rate_limiter._check_rate_limit("test_user_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_over_limit(self, rate_limiter, mock_db):
        """Test rate limit check when user is over the limit."""
        # Mock database response - user has made 6 queries today (over limit)
        mock_result = Mock()
        mock_result.result_set = [[6]]  # Current count
        mock_db.query.return_value = mock_result

        result = await rate_limiter._check_rate_limit("test_user_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_no_queries_today(self, rate_limiter, mock_db):
        """Test rate limit check when user has made no queries today."""
        # Mock database response - no query count record for today
        mock_result = Mock()
        mock_result.result_set = [[0]]  # COALESCE returns 0
        mock_db.query.return_value = mock_result

        result = await rate_limiter._check_rate_limit("test_user_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_database_error(self, rate_limiter, mock_db):
        """Test rate limit check when database error occurs."""
        # Mock database error
        mock_db.query.side_effect = Exception("Database connection error")

        result = await rate_limiter._check_rate_limit("test_user_123")
        assert result is True  # Should allow request on database error

    @pytest.mark.asyncio
    async def test_increment_query_count_new_user(self, rate_limiter, mock_db):
        """Test incrementing query count for a new user."""
        # Mock database response - new count created
        mock_result = Mock()
        mock_result.result_set = [[1]]  # New count
        mock_db.query.return_value = mock_result

        await rate_limiter._increment_query_count("test_user_123")

        # Verify correct query was called
        mock_db.query.assert_called_once()
        call_args = mock_db.query.call_args
        query_str = call_args[0][0]  # First positional argument
        params = call_args[0][1]     # Second positional argument
        
        assert "MERGE" in query_str
        assert "ON CREATE SET qc.count = 1" in query_str
        assert params["user_id"] == "test_user_123"
        assert "today" in params

    @pytest.mark.asyncio
    async def test_increment_query_count_existing_user(self, rate_limiter, mock_db):
        """Test incrementing query count for an existing user."""
        # Mock database response - count incremented
        mock_result = Mock()
        mock_result.result_set = [[4]]  # Incremented count
        mock_db.query.return_value = mock_result

        await rate_limiter._increment_query_count("test_user_123")

        # Verify correct query was called
        mock_db.query.assert_called_once()
        call_args = mock_db.query.call_args
        assert "ON MATCH SET qc.count = qc.count + 1" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_increment_query_count_database_error(self, rate_limiter, mock_db):
        """Test incrementing query count when database error occurs."""
        # Mock database error
        mock_db.query.side_effect = Exception("Database connection error")

        # Should not raise exception on database error
        await rate_limiter._increment_query_count("test_user_123")

    @pytest.mark.asyncio
    async def test_check_and_increment_rate_limit_success(self, rate_limiter, mock_db):
        """Test successful rate limit check and increment."""
        # Mock database responses
        check_result = Mock()
        check_result.result_set = [[2]]  # Under limit
        increment_result = Mock()
        increment_result.result_set = [[3]]  # Incremented count
        mock_db.query.side_effect = [check_result, increment_result]

        # Should not raise exception
        await rate_limiter.check_and_increment_rate_limit("test_user_123")

        # Verify both queries were called
        assert mock_db.query.call_count == 2

    @pytest.mark.asyncio
    async def test_check_and_increment_rate_limit_exceeded(self, rate_limiter, mock_db):
        """Test rate limit check when limit is exceeded."""
        # Mock database response - over limit
        mock_result = Mock()
        mock_result.result_set = [[5]]  # At limit
        mock_db.query.return_value = mock_result

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await rate_limiter.check_and_increment_rate_limit("test_user_123")

        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Daily query limit exceeded" in exc_info.value.detail
        assert "5 queries per day" in exc_info.value.detail

        # Should only call check query, not increment
        assert mock_db.query.call_count == 1

    @patch('api.rate_limiter.datetime')
    @pytest.mark.asyncio
    async def test_uses_utc_date(self, mock_datetime, rate_limiter, mock_db):
        """Test that rate limiting uses UTC date consistently."""
        # Mock current UTC time
        mock_now = Mock()
        mock_now.strftime.return_value = "2024-01-15"
        mock_datetime.now.return_value = mock_now

        mock_result = Mock()
        mock_result.result_set = [[0]]
        mock_db.query.return_value = mock_result

        await rate_limiter._check_rate_limit("test_user_123")

        # Verify UTC timezone was used
        mock_datetime.now.assert_called_with(timezone.utc)
        # Verify date format
        mock_now.strftime.assert_called_with("%Y-%m-%d")
        # Verify date was passed to query
        call_args = mock_db.query.call_args
        params = call_args[0][1]  # Second positional argument
        assert params["today"] == "2024-01-15"