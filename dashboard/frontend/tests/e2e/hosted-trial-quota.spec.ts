import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { expect, test } from "@playwright/test";
import {
  createPublicationSlotReserver,
  isPublicationProducingRequest,
  weekKey,
  type PublicationLedger,
} from "../../src/lib/hosted-trial-quota";

async function readLedger(path: string): Promise<PublicationLedger> {
  return JSON.parse(await readFile(path, "utf8")) as PublicationLedger;
}

test.describe("hosted trial publication quota", () => {
  test("classifies only publication-producing project mutations", () => {
    expect(
      isPublicationProducingRequest(
        ["projects", "project-1", "stages", "paper", "run"],
        new Request("http://localhost/api/v1/projects/project-1/stages/paper/run", {
          method: "POST",
        }),
      ),
    ).toBe(true);
    expect(
      isPublicationProducingRequest(
        ["projects", "project-1", "publications"],
        new Request("http://localhost/api/v1/projects/project-1/publications", {
          method: "POST",
        }),
      ),
    ).toBe(true);
    expect(
      isPublicationProducingRequest(
        ["projects", "project-1", "stages", "results", "run"],
        new Request("http://localhost/api/v1/projects/project-1/stages/results/run", {
          method: "POST",
        }),
      ),
    ).toBe(false);
    expect(
      isPublicationProducingRequest(
        ["projects", "project-1", "publications"],
        new Request("http://localhost/api/v1/projects/project-1/publications"),
      ),
    ).toBe(false);
  });

  test("limits trial tenants by weekly publication count and reports quota state", async () => {
    const dir = await mkdtemp(join(tmpdir(), "plato-trial-quota-"));
    const ledgerPath = join(dir, "weekly-publications.json");
    const now = () => new Date("2026-05-19T12:00:00.000Z");
    const reservePublicationSlot = createPublicationSlotReserver({
      ledgerPath,
      limit: 2,
      shouldApplyLimit: async () => true,
      now,
    });

    try {
      const first = await reservePublicationSlot("lab_org_1");
      const second = await reservePublicationSlot("lab_org_1");
      const third = await reservePublicationSlot("lab_org_1");

      expect(first.limited).toBeNull();
      expect(second.limited).toBeNull();
      expect(third.limited?.status).toBe(402);
      await expect(third.limited?.json()).resolves.toMatchObject({
        code: "trial_publication_limit_exceeded",
        week: weekKey(now()),
        used: 2,
        limit: 2,
      });

      const ledger = await readLedger(ledgerPath);
      expect(ledger.lab_org_1[weekKey(now())].publications).toBe(2);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  test("rolls back reserved quota when the upstream publication request fails", async () => {
    const dir = await mkdtemp(join(tmpdir(), "plato-trial-quota-"));
    const ledgerPath = join(dir, "weekly-publications.json");
    const now = () => new Date("2026-05-19T12:00:00.000Z");
    const reservePublicationSlot = createPublicationSlotReserver({
      ledgerPath,
      limit: 1,
      shouldApplyLimit: async () => true,
      now,
    });

    try {
      const reservation = await reservePublicationSlot("lab_org_2");
      await reservation.rollback();
      const retry = await reservePublicationSlot("lab_org_2");

      expect(reservation.limited).toBeNull();
      expect(retry.limited).toBeNull();

      const ledger = await readLedger(ledgerPath);
      expect(ledger.lab_org_2[weekKey(now())].publications).toBe(1);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  test("does not create a ledger when paid billing bypasses the trial limit", async () => {
    const dir = await mkdtemp(join(tmpdir(), "plato-trial-quota-"));
    const ledgerPath = join(dir, "weekly-publications.json");
    const reservePublicationSlot = createPublicationSlotReserver({
      ledgerPath,
      limit: 2,
      shouldApplyLimit: async () => false,
    });

    try {
      const reservation = await reservePublicationSlot("lab_paid");

      expect(reservation.limited).toBeNull();
      await expect(stat(ledgerPath)).rejects.toMatchObject({ code: "ENOENT" });
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  test("fails closed when the quota ledger is malformed", async () => {
    const dir = await mkdtemp(join(tmpdir(), "plato-trial-quota-"));
    const ledgerPath = join(dir, "weekly-publications.json");
    await writeFile(ledgerPath, "{not-json", "utf8");
    const reservePublicationSlot = createPublicationSlotReserver({
      ledgerPath,
      limit: 2,
      shouldApplyLimit: async () => true,
    });

    try {
      const reservation = await reservePublicationSlot("lab_corrupt");

      expect(reservation.limited?.status).toBe(503);
      await expect(reservation.limited?.json()).resolves.toMatchObject({
        code: "hosted_usage_ledger_unavailable",
      });
      await expect(readFile(ledgerPath, "utf8")).resolves.toBe("{not-json");
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});
