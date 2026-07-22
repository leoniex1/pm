import { render, screen } from "@testing-library/react";
import LoginPage from "@/app/login/page";

describe("LoginPage", () => {
  beforeEach(() => {
    global.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ authenticated: false, username: null }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
    ) as typeof fetch;
  });

  it("does not prefill username or password", async () => {
    render(<LoginPage />);

    expect(await screen.findByLabelText("Username")).toHaveValue("");
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });
});
