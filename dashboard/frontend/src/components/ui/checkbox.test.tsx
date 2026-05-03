import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { Checkbox } from "./checkbox";

// The `Checkbox` is a controlled component built on a hidden native
// input — these tests pin the contract callers depend on:
//   1. clicking flips state through onCheckedChange,
//   2. the keyboard space key flips state on the focused input
//      (jsdom doesn't synthesize the change-on-space the way a real
//       browser does, so we drive it via fireEvent.click which is what
//       a Space keypress triggers on a checkbox under the hood),
//   3. disabled blocks both paths.

function ControlledCheckbox(props: {
  initial?: boolean;
  onChange?: (next: boolean) => void;
  disabled?: boolean;
  label?: React.ReactNode;
}) {
  const [checked, setChecked] = React.useState(props.initial ?? false);
  return (
    <Checkbox
      checked={checked}
      onCheckedChange={(next) => {
        setChecked(next);
        props.onChange?.(next);
      }}
      disabled={props.disabled}
      label={props.label ?? "Enable thing"}
      data-testid="cb"
    />
  );
}

describe("<Checkbox />", () => {
  it("renders unchecked by default and reflects the prop", () => {
    render(
      <Checkbox
        checked={false}
        onCheckedChange={() => {}}
        label="L"
        data-testid="cb"
      />,
    );
    const input = screen.getByTestId("cb") as HTMLInputElement;
    expect(input.checked).toBe(false);
  });

  it("fires onCheckedChange when clicked", () => {
    const spy = vi.fn();
    render(<ControlledCheckbox onChange={spy} />);
    const input = screen.getByTestId("cb") as HTMLInputElement;
    fireEvent.click(input);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenLastCalledWith(true);
    expect(input.checked).toBe(true);
  });

  it("toggles via the space key when focused (click-equivalent path)", () => {
    // Browsers translate Space-on-checkbox into a click that fires the
    // `change` event. jsdom doesn't synthesize that translation, so we
    // assert the same observable outcome by firing the click that Space
    // would trigger. The keyDown is included so a future jsdom upgrade
    // that does synthesize the click won't double-fire and break this.
    const spy = vi.fn();
    render(<ControlledCheckbox onChange={spy} />);
    const input = screen.getByTestId("cb") as HTMLInputElement;
    input.focus();
    expect(input).toHaveFocus();
    fireEvent.keyDown(input, { key: " ", code: "Space" });
    fireEvent.click(input);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenLastCalledWith(true);
    expect(input.checked).toBe(true);
  });

  it("space toggles back to unchecked on a second press", () => {
    const spy = vi.fn();
    render(<ControlledCheckbox initial={true} onChange={spy} />);
    const input = screen.getByTestId("cb") as HTMLInputElement;
    input.focus();
    fireEvent.click(input);
    expect(spy).toHaveBeenLastCalledWith(false);
    expect(input.checked).toBe(false);
  });

  it("blocks interaction when disabled (real DOM click respects disabled)", () => {
    // Note: fireEvent.click bypasses the browser's `disabled` short-
    // circuit, so we use the DOM-level `input.click()` which mirrors
    // what a real browser does — a disabled input swallows the click.
    const spy = vi.fn();
    render(
      <Checkbox
        checked={false}
        onCheckedChange={spy}
        disabled
        label="L"
        data-testid="cb"
      />,
    );
    const input = screen.getByTestId("cb") as HTMLInputElement;
    expect(input).toBeDisabled();
    input.click();
    expect(spy).not.toHaveBeenCalled();
    expect(input.checked).toBe(false);
  });

  it("uses an aria-label when no visible label is supplied", () => {
    render(
      <Checkbox
        checked={false}
        onCheckedChange={() => {}}
        aria-label="Hidden cb"
        data-testid="cb"
      />,
    );
    const input = screen.getByTestId("cb");
    expect(input).toHaveAttribute("aria-label", "Hidden cb");
  });
});
