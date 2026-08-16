// Focused regression verification for the client-side silent token refresh
// flow (single-flight deduplication + loop protection + refresh failure).
//
// The orchestration lives in src/lib/token-refresh.ts with injected storage
// and network dependencies, so Node can run it directly via type stripping:
//
//   node --experimental-strip-types scripts/test-token-refresh.mts
//
// Exit status is non-zero if any check fails.

import {
  isRefreshableRequest,
  refreshAccessToken,
  resetTokenRefresh,
  type RefreshApi,
  type TokenStorage,
} from "../src/lib/token-refresh.ts";

const checks = [];

function check(name, passed, detail = "") {
  checks.push({ name, passed, detail });
}

function makeStorage(initial) {
  let tokens = initial;
  return {
    getStoredTokens: () => tokens,
    storeTokens: (next) => {
      tokens = next;
    },
    clearStoredTokens: () => {
      tokens = null;
    },
  };
}

function makeApi(refreshCalls, fail = false, delayMs = 0) {
  return {
    refresh: async (token) => {
      refreshCalls.count += 1;
      if (delayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
      if (fail) throw new Error("refresh failed");
      return {
        access_token: `new-access-${token}`,
        refresh_token: "new-refresh",
        token_type: "bearer",
      };
    },
  };
}

// 1. Loop protection: excluded paths and retried requests never refresh again.
check(
  "1. login path never triggers a refresh",
  isRefreshableRequest("/auth/login", false) === false,
);
check(
  "1. refresh path never triggers a refresh",
  isRefreshableRequest("/auth/refresh", false) === false,
);
check(
  "1. refresh path with query never triggers a refresh",
  isRefreshableRequest("/auth/refresh?device=web", false) === false,
);
check(
  "1. normal authenticated path is refreshable",
  isRefreshableRequest("/documents", false) === true,
);
check(
  "1. already-retried request is never refreshed again",
  isRefreshableRequest("/documents", true) === false,
);
check(
  "1. missing url without a retry is refreshable",
  isRefreshableRequest(undefined, false) === true,
);
check(
  "1. missing url after a retry is not refreshable",
  isRefreshableRequest(undefined, true) === false,
);

// 2. Single-flight: concurrent 401s share exactly one refresh call and all
//    callers resolve with the same freshly issued access token.
resetTokenRefresh();
const refreshCalls = { count: 0 };
const storage2 = makeStorage({ accessToken: "old-access", refreshToken: "old-refresh" });
const api2 = makeApi(refreshCalls, false, 10);
const [first, second] = await Promise.all([
  refreshAccessToken(api2, storage2),
  refreshAccessToken(api2, storage2),
]);
check(
  "2. concurrent 401s share one refresh call",
  refreshCalls.count === 1 && first === "new-access-old-refresh" && second === "new-access-old-refresh",
);
check(
  "2. new token pair is stored once",
  storage2.getStoredTokens()?.accessToken === "new-access-old-refresh" &&
    storage2.getStoredTokens()?.refreshToken === "new-refresh",
);

// 3. Refresh failure rejects, leaves stored tokens untouched (logout is the
//    caller's job), and resets so a later attempt can succeed.
resetTokenRefresh();
const refreshCalls3 = { count: 0 };
const storage3 = makeStorage({ accessToken: "a1", refreshToken: "r1" });
const api3 = makeApi(refreshCalls3, true);
let threw = false;
try {
  await refreshAccessToken(api3, storage3);
} catch {
  threw = true;
}
check("3. refresh failure rejects", threw === true);
check(
  "3. failed refresh keeps the stored tokens",
  storage3.getStoredTokens()?.accessToken === "a1" &&
    storage3.getStoredTokens()?.refreshToken === "r1",
);
const api3ok = makeApi(refreshCalls3, false);
const recovered = await refreshAccessToken(api3ok, storage3);
check(
  "3. a later refresh can succeed after a failure",
  recovered === "new-access-r1" && refreshCalls3.count === 2,
);

// 4. No stored refresh token rejects without calling the network.
resetTokenRefresh();
const refreshCalls4 = { count: 0 };
const storage4 = makeStorage(null);
const api4 = makeApi(refreshCalls4);
let threw4 = false;
try {
  await refreshAccessToken(api4, storage4);
} catch {
  threw4 = true;
}
check(
  "4. missing stored refresh token rejects without a network call",
  threw4 === true && refreshCalls4.count === 0,
);

let failed = 0;
for (const { name, passed, detail } of checks) {
  const status = passed ? "PASS" : "FAIL";
  if (!passed) failed += 1;
  console.log(`${name.padEnd(58)}${status}`);
  if (!passed && detail) console.log(`  ${detail}`);
}

console.log("\n" + (failed === 0 ? "PASS" : `FAIL (${failed}/${checks.length})`));
process.exit(failed === 0 ? 0 : 1);