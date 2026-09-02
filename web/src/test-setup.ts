// Unmount what each test rendered. Testing Library only registers this itself
// when the runner exposes globals, which vitest does not by default.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);
