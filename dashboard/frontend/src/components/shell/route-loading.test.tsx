import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RouteLoading } from "./route-loading";

describe("<RouteLoading />", () => {
  it("renders the provided label", () => {
    render(<RouteLoading label="Test" />);
    expect(screen.getByText("Test")).toBeInTheDocument();
  });

  it("falls back to the default label when none is supplied", () => {
    render(<RouteLoading />);
    expect(screen.getByText(/Loading/i)).toBeInTheDocument();
  });

  it("exposes the loading state to assistive tech", () => {
    render(<RouteLoading label="Fetching runs" />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveAttribute("data-testid", "route-loading");
  });
});
