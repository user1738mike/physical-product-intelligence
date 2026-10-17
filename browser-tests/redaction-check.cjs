const assert = require("node:assert/strict");
const { redactText } = require("./redact-results.cjs");
const credential = "ppi_i_" + "a".repeat(32) + "." + "b".repeat(43);
const signing = "whsec_" + "c".repeat(43) + "=";
const output = redactText(
  JSON.stringify({
    secret: credential,
    signing,
    password: "synthetic-password",
  }),
  ["synthetic-password"],
);
assert(!output.includes(credential));
assert(!output.includes(signing));
assert(!output.includes('"synthetic-password"'));
assert(output.includes("[redacted-api-credential]"));
