const fs = require("node:fs");
const path = require("node:path");
const fixture = JSON.parse(
  fs.readFileSync("/tmp/ppi-browser-journey.json", "utf8"),
);
const passwords = [fixture.owner.password, fixture.outsider.password];
function redact(directory) {
  for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, item.name);
    if (item.isDirectory()) redact(file);
    else if (item.isFile() && /\.(json|md|log|txt)$/.test(item.name)) {
      let text = fs.readFileSync(file, "utf8");
      for (const password of passwords)
        text = text.replaceAll(password, "[redacted-synthetic-password]");
      fs.writeFileSync(file, text);
    }
  }
}
redact("/results");
