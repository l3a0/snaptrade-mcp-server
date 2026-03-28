"""Type stubs for snaptrade_client library."""

from typing import Any, Optional

class SnapTrade:
    """SnapTrade API client."""
    
    account_information: AccountInformationAPI
    transactions_and_reporting: TransactionsAndReportingAPI
    reference_data: ReferenceDataAPI
    authentication: AuthenticationAPI
    
    def __init__(self, consumer_key: str, client_id: str) -> None: ...

class AccountInformationAPI:
    """Account information endpoints."""
    
    def list_user_accounts(
        self,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        query_params: Optional[dict[str, Any]] = None,
    ) -> Any: ...
    
    def get_user_account_balance(
        self,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        account_id: Optional[str] = None,
        query_params: Optional[dict[str, Any]] = None,
        path_params: Optional[dict[str, Any]] = None,
    ) -> Any: ...
    
    def get_user_account_positions(
        self,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        account_id: Optional[str] = None,
        query_params: Optional[dict[str, Any]] = None,
        path_params: Optional[dict[str, Any]] = None,
    ) -> Any: ...
    
    def get_user_account_orders(
        self,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        account_id: Optional[str] = None,
        state: Optional[str] = None,
        days: Optional[int] = None,
        query_params: Optional[dict[str, Any]] = None,
        path_params: Optional[dict[str, Any]] = None,
    ) -> Any: ...

class TransactionsAndReportingAPI:
    """Transactions and reporting endpoints."""
    
    def get_activities(
        self,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        accounts: Optional[str] = None,
        brokerage_authorizations: Optional[str] = None,
        type: Optional[str] = None,
        query_params: Optional[dict[str, Any]] = None,
    ) -> Any: ...

class ReferenceDataAPI:
    """Reference data endpoints."""
    
    def symbol_search_user_account(
        self,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        account_id: Optional[str] = None,
        body: Optional[dict[str, Any]] = None,
        substring: Optional[str] = None,
        query_params: Optional[dict[str, Any]] = None,
        path_params: Optional[dict[str, Any]] = None,
    ) -> Any: ...
    
    def list_all_brokerages(self) -> Any: ...

class AuthenticationAPI:
    """Authentication endpoints."""
    
    def register_snap_trade_user(
        self,
        body: Optional[dict[str, Any]] = None,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        query_params: Optional[dict[str, Any]] = None,
    ) -> Any: ...
    
    def login_snap_trade_user(
        self,
        body: Optional[dict[str, Any]] = None,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        broker: Optional[str] = None,
        immediate_redirect: Optional[bool] = None,
        custom_redirect: Optional[str] = None,
        reconnect: Optional[str] = None,
        connection_type: Optional[str] = None,
        connection_portal_version: Optional[str] = None,
        query_params: Optional[dict[str, Any]] = None,
    ) -> Any: ...
