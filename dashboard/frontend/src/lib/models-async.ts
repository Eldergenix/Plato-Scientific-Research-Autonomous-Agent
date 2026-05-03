// Async accessors that defer the model catalog out of the importing
// module's chunk. Routes that don't *need* the catalog statically (the
// home shell, run detail pages, the sidebar) call these at mount or
// on-demand so the ~5 kB JSON literal lands in a separate chunk that
// only downloads when the picker opens.
import type { ModelDef } from "./types";

type Catalog = typeof import("./models-catalog");

let cached: Catalog | null = null;
let pending: Promise<Catalog> | null = null;

export function loadModelsCatalog(): Promise<Catalog> {
  if (cached) return Promise.resolve(cached);
  if (!pending) {
    pending = import("./models-catalog").then((mod) => {
      cached = mod;
      return mod;
    });
  }
  return pending;
}

export function getCachedModelsCatalog(): Catalog | null {
  return cached;
}

export async function getModelById(id: string): Promise<ModelDef | undefined> {
  const cat = await loadModelsCatalog();
  return cat.MODELS_BY_ID[id];
}
