import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

describe("vitest harness", () => {
  it("renders a simple element", () => {
    render(<div>Hello</div>);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });
});
