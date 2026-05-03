import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OnboardingEmptyState } from "./empty-state";

// The checklist mirrors `done` straight from the props, and the icon's
// `aria-label` flips between "Step complete" / "Step incomplete". We
// assert against those rather than CSS classes so the test survives a
// Tailwind/theme refactor.
function getStep(id: "key" | "domain" | "run") {
  return screen.getByTestId(`onboarding-step-${id}`);
}

function isStepDone(id: "key" | "domain" | "run") {
  return getStep(id).getAttribute("data-done") === "true";
}

describe("<OnboardingEmptyState />", () => {
  it("shows all three steps incomplete when nothing is configured", () => {
    render(<OnboardingEmptyState hasApiKey={false} hasProject={false} />);
    expect(isStepDone("key")).toBe(false);
    expect(isStepDone("domain")).toBe(false);
    expect(isStepDone("run")).toBe(false);
    expect(screen.getByText(/0 of 3 complete/i)).toBeInTheDocument();
  });

  it("checks only the API-key step when a key is set", () => {
    render(<OnboardingEmptyState hasApiKey={true} hasProject={false} />);
    expect(isStepDone("key")).toBe(true);
    expect(isStepDone("domain")).toBe(false);
    expect(isStepDone("run")).toBe(false);
    expect(screen.getByText(/1 of 3 complete/i)).toBeInTheDocument();
  });

  it("checks only the domain step when a project exists", () => {
    render(<OnboardingEmptyState hasApiKey={false} hasProject={true} />);
    expect(isStepDone("key")).toBe(false);
    expect(isStepDone("domain")).toBe(true);
    expect(isStepDone("run")).toBe(false);
    expect(screen.getByText(/1 of 3 complete/i)).toBeInTheDocument();
  });

  it("checks both steps when key + project are set, and run stays open", () => {
    render(<OnboardingEmptyState hasApiKey={true} hasProject={true} />);
    expect(isStepDone("key")).toBe(true);
    expect(isStepDone("domain")).toBe(true);
    // The run step is the user's CTA — never marked done by props alone.
    expect(isStepDone("run")).toBe(false);
    expect(screen.getByText(/2 of 3 complete/i)).toBeInTheDocument();
  });

  it("renders a CTA link to /keys for the API key step", () => {
    render(<OnboardingEmptyState hasApiKey={false} hasProject={false} />);
    const link = screen.getByRole("link", { name: /open \/keys/i });
    expect(link).toHaveAttribute("href", "/keys");
  });

  it("uses an aria-live region for the progress counter", () => {
    render(<OnboardingEmptyState hasApiKey={true} hasProject={false} />);
    const progress = screen.getByText(/1 of 3 complete/i);
    expect(progress).toHaveAttribute("aria-live", "polite");
  });
});
