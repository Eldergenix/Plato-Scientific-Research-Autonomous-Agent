"""Experiment output files: which ones a run keeps, how they are recorded, and the schema
rules that protect their names (tables, structures and networks shown in the app)."""

from __future__ import annotations

import pytest

from plato.scientist.db.store import valid_file_name
from plato.scientist.guard import run_python
from plato.scientist.nodes import MAX_DATA_BYTES, MAX_DATA_FILES, MAX_PLOTS, store_outputs


@pytest.mark.parametrize(
    "name,ok",
    [
        ("volcano.csv", True),
        ("1UBQ clean.pdb", True),
        ("a" * 255, True),
        ("", False),
        ("a" * 256, False),
        ("../secret.csv", False),
        ("dir/file.csv", False),
        ("dir\\file.csv", False),
        (".hidden.csv", False),
        ("tab\there.csv", False),
        ("bell\x07.csv", False),
    ],
)
def test_file_names_are_bare(name, ok):
    assert valid_file_name(name) is ok


async def test_sandbox_collects_structures_tables_and_networks():
    code = (
        "for n in ['m.pdb', 'lig.SDF', 't.tsv', 'net.sif', 'g.graphml', 'x.cif', 'skip.bin']:\n"
        "    open(n, 'w').write('x')\n"
        "print('PLATO_METRICS {\"k\": 1}')\n"
    )
    res = await run_python(code, inputs={"plato_seed.txt": b"1"})
    assert res.ok, res.stderr
    assert set(res.files) == {"m.pdb", "lig.SDF", "t.tsv", "net.sif", "g.graphml", "x.cif"}


async def _fact(store, campaign):
    _, cid = campaign
    intent = await store.create_node(cid, "intent", "x", "{}")
    claimed = await store.claim_next_intent(cid, "w1")
    assert claimed["id"] == intent.id
    return await store.record_fact(cid, intent.id, "w1", title="t", observation="o")


async def test_store_outputs_records_plots_and_data_files_with_names(store, campaign):
    fact = await _fact(store, campaign)
    files = {
        "volcano.png": b"\x89PNG fake",
        "diff.csv": b"gene,log2FC\nA,1\n",
        "model.pdb": b"ATOM      1  CA  ALA A   1",
        "pathway.sif": b"A\tactivation\tB\n",
        "notes.bin": b"ignored",
        ".hidden.csv": b"ignored",
        "empty.tsv": b"",
    }
    await store_outputs(store, fact, files)
    rows = await store.evidence_for([fact])
    got = {(r["artifact_type"], r["file_name"]) for r in rows}
    assert got == {
        ("plot_png", "volcano.png"),
        ("data_file", "diff.csv"),
        ("data_file", "model.pdb"),
        ("data_file", "pathway.sif"),
    }
    assert {r["size_bytes"] for r in rows if r["file_name"] == "diff.csv"} == {16}
    # Recording the same run again (a retried worker) adds nothing.
    await store_outputs(store, fact, files)
    assert len(await store.evidence_for([fact])) == 4


async def test_store_outputs_is_bounded(store, campaign):
    fact = await _fact(store, campaign)
    many = {f"t{i:02d}.csv": f"a\n{i}\n".encode() for i in range(MAX_DATA_FILES + 5)}
    many.update({f"p{i:02d}.png": f"png{i}".encode() for i in range(MAX_PLOTS + 3)})
    await store_outputs(store, fact, many)
    rows = await store.evidence_for([fact])
    assert sum(r["artifact_type"] == "data_file" for r in rows) == MAX_DATA_FILES
    assert sum(r["artifact_type"] == "plot_png" for r in rows) == MAX_PLOTS

    fact2 = await _fact(store, campaign)
    big = 1_000_000  # under the 1 MiB inline limit each; seven exceed the 6 MiB budget
    files = {f"s{i}.pdb": bytes([65 + i]) * big for i in range(8)} | {"small.csv": b"a\n1\n"}
    await store_outputs(store, fact2, files)
    rows = await store.evidence_for([fact2])
    kept = sum(r["size_bytes"] for r in rows)
    assert kept <= MAX_DATA_BYTES
    assert "small.csv" in {r["file_name"] for r in rows}  # smallest first, so it always fits


async def test_schema_rejects_paths_in_file_names(store, campaign):
    fact = await _fact(store, campaign)
    with pytest.raises(ValueError):
        await store.add_evidence(fact, "data_file", b"x", file_name="../x.csv")
    import asyncpg

    with pytest.raises(asyncpg.CheckViolationError):
        await store._pool.execute(
            "INSERT INTO plato.evidence_artifacts (node_id, artifact_type, storage_uri, sha256_checksum, content, approval_actor, file_name)"
            " VALUES ($1, 'data_file', 'inline', encode(sha256('x'::bytea), 'hex'), 'x'::bytea, 'system', 'a/b.csv')",
            fact,
        )
    with pytest.raises(asyncpg.CheckViolationError):
        await store._pool.execute(
            "INSERT INTO plato.evidence_artifacts (node_id, artifact_type, storage_uri, sha256_checksum, content, approval_actor)"
            " VALUES ($1, 'not_a_type', 'inline', encode(sha256('y'::bytea), 'hex'), 'y'::bytea, 'system')",
            fact,
        )
