const fs = require("node:fs");
const path = require("node:path");
function redactText(text, passwords = []) {
  for (const password of passwords)
    text = text.replaceAll(password, "[redacted-synthetic-password]");
  return text
    .replace(
      /ppi_i_[0-9a-f]{32}\.[A-Za-z0-9_-]{43}/g,
      "[redacted-api-credential]",
    )
    .replace(/whsec_[A-Za-z0-9+/=]+/g, "[redacted-webhook-secret]");
}
function redact(directory, passwords) {
  for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, item.name);
    if (item.isDirectory()) redact(file, passwords);
    else if (item.isFile() && /\.(json|md|log|txt)$/.test(item.name)) {
      fs.writeFileSync(
        file,
        redactText(fs.readFileSync(file, "utf8"), passwords),
      );
    }
  }
}
if (require.main === module) {
  const fixture = JSON.parse(
    fs.readFileSync("/tmp/ppi-browser-journey.json", "utf8"),
  );
  const passwords = [fixture.owner.password, fixture.outsider.password];
  const report = "/tmp/ppi-browser.json",
    output = "/tmp/ppi-playwright-output";
  if (fs.existsSync(report))
    fs.writeFileSync(
      "/results/browser.json",
      redactText(fs.readFileSync(report, "utf8"), passwords),
    );
  if (fs.existsSync(output)) {
    redact(output, passwords);
    fs.cpSync(output, "/results/run", { recursive: true });
  }
  redact("/results", passwords);
  process.stdout.write(
    redactText(
      fs.readFileSync("/tmp/ppi-browser-console.log", "utf8"),
      passwords,
    ),
  );
}
module.exports = { redactText };
