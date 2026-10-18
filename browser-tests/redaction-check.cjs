const assert = require("node:assert/strict");
const { redactText } = require("./redact-results.cjs");
const credential = "ppi_i_" + "a".repeat(32) + "." + "b".repeat(43);
const signing = "whsec_" + "c".repeat(43) + "=";
const recovery = "d".repeat(32) + "." + "e".repeat(43);
const output = redactText(
  JSON.stringify({
    secret: credential,
    signing,
    recovery,
    password: "synthetic-password",
    request:
      "cookie: sessionid=synthetic-session; csrftoken=synthetic-csrf\nauthorization: Bearer synthetic-bearer\nx-csrftoken: synthetic-masked-token\nnext: retained",
  }),
  ["synthetic-password"],
);
assert(!output.includes(credential));
assert(!output.includes(signing));
assert(!output.includes(recovery));
assert(!output.includes('"synthetic-password"'));
assert(output.includes("[redacted-api-credential]"));
for (const value of [
  "synthetic-session",
  "synthetic-csrf",
  "synthetic-bearer",
  "synthetic-masked-token",
])
  assert(!output.includes(value));
assert(JSON.parse(output).request.includes("next: retained"));
assert(
  !redactText("sessionid=synthetic-session; csrftoken=synthetic-csrf").includes(
    "synthetic-",
  ),
);
for (const message of [
  "cookie: sessionid=synthetic-session",
  "set-cookie: csrftoken=synthetic-csrf; Secure",
  "authorization: Bearer synthetic-bearer",
  "x-csrftoken: synthetic-masked-token",
]) {
  const json = redactText(JSON.stringify({ message }));
  assert(!json.includes("synthetic-"));
  assert.equal(typeof JSON.parse(json).message, "string");
}
