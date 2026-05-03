import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sheet } from "./sheet";

// jsdom defaults `matchMedia` to undefined; the Sheet's swipe-to-dismiss
// branch reads it to gate mobile-only behavior. Fake-mobile here so the
// gesture handler runs end-to-end.
function installMatchMedia(matches: (query: string) => boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: matches(query),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

beforeEach(() => {
  // Pretend we're on a mobile viewport so the swipe handler engages.
  installMatchMedia((q) => q.includes("max-width: 768px"));
  // jsdom lacks `setPointerCapture` / `releasePointerCapture`. The
  // Sheet's gesture code guards against missing methods, but several
  // versions of jsdom throw on `hasPointerCapture` so stub it too.
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = vi.fn();
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
});

afterEach(() => {
  vi.restoreAllMocks();
});

function ControlledSheet(props: { onOpenChange: (next: boolean) => void }) {
  const [open, setOpen] = React.useState(true);
  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        props.onOpenChange(next);
      }}
      title="Test"
      side="left"
    >
      <div data-testid="sheet-body" style={{ height: 300 }}>
        body
      </div>
    </Sheet>
  );
}

describe("<Sheet /> swipe-to-dismiss", () => {
  it("renders children when open", () => {
    const spy = vi.fn();
    render(<ControlledSheet onOpenChange={spy} />);
    expect(screen.getByTestId("sheet-body")).toBeInTheDocument();
    expect(screen.getByTestId("sheet-content")).toHaveAttribute(
      "data-side",
      "left",
    );
  });

  it("calls onOpenChange(false) after a leftward swipe past the threshold", () => {
    const spy = vi.fn();
    render(<ControlledSheet onOpenChange={spy} />);
    const content = screen.getByTestId("sheet-content");

    // Pointer flow: down at (200,200) -> move past axis-lock threshold
    // (8px) -> move past dismiss threshold (50px) -> up.
    fireEvent.pointerDown(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 200,
      clientY: 200,
    });
    fireEvent.pointerMove(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 180, // 20px left — passes axis lock, stays under dismiss
      clientY: 200,
    });
    fireEvent.pointerMove(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 120, // 80px left — past 50px dismiss threshold
      clientY: 200,
    });
    fireEvent.pointerUp(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 120,
      clientY: 200,
    });

    expect(spy).toHaveBeenCalledWith(false);
  });

  it("does NOT close on a small swipe under the threshold", () => {
    const spy = vi.fn();
    render(<ControlledSheet onOpenChange={spy} />);
    const content = screen.getByTestId("sheet-content");

    fireEvent.pointerDown(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 200,
      clientY: 200,
    });
    // 30px left is past axis-lock (8px) but under dismiss (50px).
    fireEvent.pointerMove(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 170,
      clientY: 200,
    });
    fireEvent.pointerUp(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 170,
      clientY: 200,
    });

    expect(spy).not.toHaveBeenCalledWith(false);
  });

  it("ignores mouse pointers (mobile-touch only)", () => {
    const spy = vi.fn();
    render(<ControlledSheet onOpenChange={spy} />);
    const content = screen.getByTestId("sheet-content");

    fireEvent.pointerDown(content, {
      pointerId: 2,
      pointerType: "mouse",
      clientX: 200,
      clientY: 200,
    });
    fireEvent.pointerMove(content, {
      pointerId: 2,
      pointerType: "mouse",
      clientX: 50,
      clientY: 200,
    });
    fireEvent.pointerUp(content, {
      pointerId: 2,
      pointerType: "mouse",
      clientX: 50,
      clientY: 200,
    });

    expect(spy).not.toHaveBeenCalledWith(false);
  });

  it("abandons the swipe when motion is mostly vertical", () => {
    const spy = vi.fn();
    render(<ControlledSheet onOpenChange={spy} />);
    const content = screen.getByTestId("sheet-content");

    fireEvent.pointerDown(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 200,
      clientY: 200,
    });
    // First move is more vertical than horizontal — gesture aborts.
    fireEvent.pointerMove(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 195,
      clientY: 250,
    });
    fireEvent.pointerMove(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 100, // even a long horizontal drag now should not dismiss
      clientY: 260,
    });
    fireEvent.pointerUp(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 100,
      clientY: 260,
    });

    expect(spy).not.toHaveBeenCalledWith(false);
  });

  it("does not engage the swipe handler on non-mobile widths", () => {
    // Override matchMedia so the breakpoint check returns false.
    installMatchMedia(() => false);
    const spy = vi.fn();
    render(<ControlledSheet onOpenChange={spy} />);
    const content = screen.getByTestId("sheet-content");

    fireEvent.pointerDown(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 200,
      clientY: 200,
    });
    fireEvent.pointerMove(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 50,
      clientY: 200,
    });
    fireEvent.pointerUp(content, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 50,
      clientY: 200,
    });

    expect(spy).not.toHaveBeenCalledWith(false);
  });
});
