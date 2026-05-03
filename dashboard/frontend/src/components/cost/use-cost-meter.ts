"use client";

import * as React from "react";

// Tiny open/close hook used by the home shell. Lives in its own module so
// importing it doesn't pull `cost-meter-panel.tsx` (and the model catalog
// it references) into the home page bundle. The panel itself is loaded
// dynamically via `next/dynamic` only when the meter is opened.
export function useCostMeter() {
  const [open, setOpen] = React.useState(false);
  return {
    open,
    openMeter: () => setOpen(true),
    closeMeter: () => setOpen(false),
    onOpenChange: setOpen,
  };
}
