import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

export type PublicationLedger = Record<
  string,
  Record<string, { publications: number; updatedAt: string }>
>;

export type PublicationReservation = {
  limited: Response | null;
  rollback: () => Promise<void>;
};

type PublicationSlotReserverOptions = {
  ledgerPath: string;
  limit: number;
  shouldApplyLimit: () => Promise<boolean>;
  now?: () => Date;
};

export function parseEnvNumber(name: string, fallback: number): number {
  const raw = process.env[name]?.trim();
  if (!raw) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function isPublicationProducingRequest(path: string[], request: Request): boolean {
  return (
    request.method === "POST" &&
    path[0] === "projects" &&
    (
      (
        path.length === 5 &&
        path[2] === "stages" &&
        path[3] === "paper" &&
        path[4] === "run"
      ) ||
      (path.length === 3 && path[2] === "publications")
    )
  );
}

export function weekKey(date = new Date()): string {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

async function readLedger(ledgerPath: string): Promise<PublicationLedger> {
  try {
    return JSON.parse(await readFile(ledgerPath, "utf8")) as PublicationLedger;
  } catch (error) {
    if (
      typeof error === "object" &&
      error !== null &&
      "code" in error &&
      error.code === "ENOENT"
    ) {
      return {};
    }
    throw error;
  }
}

function ledgerUnavailableResponse(): Response {
  return Response.json(
    {
      code: "hosted_usage_ledger_unavailable",
      message: "Hosted trial quota storage is unavailable. Try again later.",
    },
    { status: 503 },
  );
}

async function writeLedger(ledgerPath: string, ledger: PublicationLedger): Promise<void> {
  await mkdir(dirname(ledgerPath), { recursive: true });
  await writeFile(ledgerPath, JSON.stringify(ledger, null, 2), "utf8");
}

export function createPublicationSlotReserver({
  ledgerPath,
  limit,
  shouldApplyLimit,
  now = () => new Date(),
}: PublicationSlotReserverOptions): (tenant: string) => Promise<PublicationReservation> {
  let ledgerWriteQueue = Promise.resolve();

  async function mutateLedger(
    update: (ledger: PublicationLedger) => Response | null | void,
  ): Promise<Response | null> {
    const writeTask = ledgerWriteQueue.then(async () => {
      try {
        const ledger = await readLedger(ledgerPath);
        const result = update(ledger) ?? null;
        if (result === null) {
          await writeLedger(ledgerPath, ledger);
        }
        return result;
      } catch {
        return ledgerUnavailableResponse();
      }
    });
    ledgerWriteQueue = writeTask.then(
      () => undefined,
      () => undefined,
    );
    return await writeTask;
  }

  return async function reservePublicationSlot(tenant: string): Promise<PublicationReservation> {
    const noopReservation = { limited: null, rollback: async () => undefined };
    if (!Number.isFinite(limit) || limit <= 0) {
      return noopReservation;
    }
    if (!(await shouldApplyLimit())) return noopReservation;

    const key = weekKey(now());
    const limited = await mutateLedger((ledger) => {
      ledger[tenant] ??= {};
      const current = ledger[tenant][key]?.publications ?? 0;
      if (current >= limit) {
        return Response.json(
          {
            code: "trial_publication_limit_exceeded",
            message: `This trial/free billing scope is limited to ${limit} scientific publications per week.`,
            week: key,
            used: current,
            limit,
          },
          { status: 402 },
        );
      }
      ledger[tenant][key] = {
        publications: current + 1,
        updatedAt: now().toISOString(),
      };
    });
    if (limited) {
      return { limited, rollback: async () => undefined };
    }

    return {
      limited: null,
      rollback: async () => {
        await mutateLedger((ledger) => {
          const current = ledger[tenant]?.[key]?.publications ?? 0;
          if (current <= 0) return;
          ledger[tenant][key] = {
            publications: current - 1,
            updatedAt: now().toISOString(),
          };
        });
      },
    };
  };
}
