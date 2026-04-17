import pytest
import responses


@pytest.fixture(autouse=True)
def _block_outbound_http():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps
