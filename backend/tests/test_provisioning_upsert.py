from contextlib import asynccontextmanager

import pytest

from app.connectors import oracle_provisioning


class FakeUpsertConnection:
    def __init__(self, existing_rows: int):
        self.existing_rows = existing_rows
        self.executed = []
        self.commits = 0
        self.rollbacks = 0
        self.fetchone_calls = 0

    async def fetchone(self, sql, parameters=None):
        self.fetchone_calls += 1
        if "COUNT(*)" in sql:
            return (self.existing_rows,)
        if ".NEXTVAL" in sql:
            return (77,)
        raise AssertionError(sql)

    async def execute(self, sql, parameters=None):
        self.executed.append((sql, parameters))
        return 1

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_table_upsert_uses_sequence_only_for_insert(monkeypatch):
    fake = FakeUpsertConnection(existing_rows=0)

    @asynccontextmanager
    async def fake_open(_connection):
        yield fake

    monkeypatch.setattr(oracle_provisioning, "open_oracle_connection", fake_open)

    result = await oracle_provisioning.upsert_oracle_provisioning_row(
        {"engine": "oracle"},
        owner="ORMS",
        table_name="USER_MASTER",
        match_values={"USERNAME": "JSMITH1001"},
        insert_values={"USERNAME": "JSMITH1001", "REMARKS": "New user"},
        update_values={"USERNAME": "JSMITH1001", "REMARKS": "New user"},
        sequence_columns={"ID": "USER_MASTER_SEQ"},
    )

    assert result["action"] == "inserted"
    assert result["generated_values"] == {"ID": 77}
    assert fake.commits == 1
    assert 'INSERT INTO "ORMS"."USER_MASTER"' in fake.executed[0][0]
    assert 77 in fake.executed[0][1].values()


@pytest.mark.asyncio
async def test_table_upsert_preserves_match_and_sequence_columns_on_update(monkeypatch):
    fake = FakeUpsertConnection(existing_rows=1)

    @asynccontextmanager
    async def fake_open(_connection):
        yield fake

    monkeypatch.setattr(oracle_provisioning, "open_oracle_connection", fake_open)

    result = await oracle_provisioning.upsert_oracle_provisioning_row(
        {"engine": "oracle"},
        owner="ORMS",
        table_name="USER_MASTER",
        match_values={"USERNAME": "JSMITH1001"},
        insert_values={"USERNAME": "JSMITH1001", "REMARKS": "Changed"},
        update_values={"USERNAME": "JSMITH1001", "REMARKS": "Changed"},
        sequence_columns={"ID": "USER_MASTER_SEQ"},
    )

    assert result["action"] == "updated"
    sql, params = fake.executed[0]
    assert 'UPDATE "ORMS"."USER_MASTER" SET "REMARKS" = :set_0' in sql
    assert '"USERNAME" = :set_' not in sql
    assert "ID" not in params
    assert fake.fetchone_calls == 1  # no NEXTVAL call on update
    assert fake.commits == 1
