"""Local tests only: run a complete research thread with the scripted test model and give
it to an account, so the export flow has a finished paper to package. Prints its id.

Run: PLATO_DATABASE_URL=... python cloudflare/plato-scientist/e2e/seed_campaign.py <account id>
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tests" / "scientist")]

from test_end_to_end import FakeModel, fake_retriever

from plato.scientist.db.store import DualGraphStore
from plato.scientist.graph import run_campaign
from plato.scientist.nodes import ScientistContext


async def main(account: uuid.UUID) -> None:
    store = await DualGraphStore.connect(os.environ["PLATO_DATABASE_URL"], max_size=10)
    try:
        program = await store.ensure_program("e2e", "E2E", "statistics")
        cid = await store.create_campaign(
            program,
            "Is the average of y greater than 2?",
            token_budget_max=1_000_000,
            config={"workers": 3, "max_rounds": 2},
            account_id=account,
        )
        train = await store.put_dataset(program, "train.csv", b"x,y\n1,2\n2,3\n3,4\n")
        await store.set_scope(cid, train.id, "train_val")
        ctx = ScientistContext(
            store=store, model=FakeModel(store), retriever=fake_retriever
        )
        summary = await run_campaign(ctx, cid)
        assert summary["campaign"]["status"] == "completed", summary["campaign"][
            "status"
        ]
        print(cid)
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main(uuid.UUID(sys.argv[1])))
