from types import SimpleNamespace

import pytest
from bson import ObjectId

from app.schemas.email_delivery import EmailDeliveryClearRequest
from app.schemas.provisioning import ProvisioningHistoryClearRequest
from app.schemas.user import UserPreferences
from app.services.email_delivery import clear_email_deliveries
from app.services.provisioning_lifecycle import clear_provisioning_runs


class RecordingCollection:
    def __init__(self, deleted_count=0):
        self.deleted_count = deleted_count
        self.last_delete_query = None

    async def delete_many(self, query):
        self.last_delete_query = query
        return SimpleNamespace(deleted_count=self.deleted_count)


class EmailDatabase:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "email_deliveries"
        return self.collection


class ProvisionDatabase:
    def __init__(self, collection):
        self.provisioning_runs = collection


def test_new_personal_preference_defaults_are_backward_compatible():
    preferences = UserPreferences()

    assert preferences.timezone == "system"
    assert preferences.date_time_format.value == "system"
    assert preferences.default_landing_page.value == "dashboard"
    assert preferences.default_history_range.value == "1h"


def test_history_clear_requests_require_a_target():
    with pytest.raises(ValueError):
        EmailDeliveryClearRequest()

    with pytest.raises(ValueError):
        ProvisioningHistoryClearRequest()

    assert EmailDeliveryClearRequest(clear_all=True).clear_all is True
    assert ProvisioningHistoryClearRequest(clear_all=True).clear_all is True


@pytest.mark.asyncio
async def test_email_clear_all_only_targets_terminal_history():
    collection = RecordingCollection(deleted_count=4)
    result = await clear_email_deliveries(
        EmailDatabase(collection),
        clear_all=True,
    )

    assert result == {"deleted_count": 4, "skipped_count": 0}
    assert collection.last_delete_query == {
        "status": {"$in": ["sent", "failed"]}
    }


@pytest.mark.asyncio
async def test_email_selected_clear_reports_protected_or_missing_rows():
    collection = RecordingCollection(deleted_count=1)
    ids = [str(ObjectId()), str(ObjectId())]

    result = await clear_email_deliveries(
        EmailDatabase(collection),
        delivery_ids=ids,
    )

    assert result["deleted_count"] == 1
    assert result["skipped_count"] == 1
    assert collection.last_delete_query["status"] == {"$in": ["sent", "failed"]}


@pytest.mark.asyncio
async def test_provision_history_clear_is_scoped_and_protects_running_runs():
    collection = RecordingCollection(deleted_count=3)
    result = await clear_provisioning_runs(
        ProvisionDatabase(collection),
        "oracle-connection-1",
        clear_all=True,
    )

    assert result == {"deleted_count": 3, "skipped_count": 0}
    assert collection.last_delete_query == {
        "parent_connection_id": "oracle-connection-1",
        "status": {"$in": ["succeeded", "partial", "failed"]},
    }
