const fs = require("fs");

const target = process.argv[2];
if (!target) throw new Error("Pass the unified HTML path as the first argument.");
const markup = fs.readFileSync(target, "utf8");
const script = markup.match(/<script>([\s\S]*)<\/script>/);
if (!script) throw new Error("Inline dashboard script is missing.");
new Function(script[1]);

const ids = [...markup.matchAll(/id="([^"]+)"/g)].map((match) => match[1]);
const duplicates = ids.filter((item, index) => ids.indexOf(item) !== index);
if (duplicates.length) throw new Error(`Duplicate HTML ids: ${duplicates.join(", ")}`);

const result = {
  javascript: "valid",
  uniqueIds: ids.length,
  tabs: (markup.match(/<button class="tab/g) || []).length,
  languageControls: (markup.match(/class="lang-btn/g) || []).length,
  englishPages: (markup.match(/data-lang="en" data-page=/g) || []).length,
  chinesePages: (markup.match(/data-lang="zh" data-page=/g) || []).length,
  page2Callouts: (markup.match(/class="callout-box"/g) || []).length,
  externalResources: /<(script[^>]+src|link|img[^>]+src)/i.test(markup),
};

if (
  result.tabs !== 3 ||
  result.languageControls !== 2 ||
  result.englishPages !== 3 ||
  result.chinesePages !== 3 ||
  result.page2Callouts !== 8 ||
  result.externalResources
) {
  throw new Error(`Structural validation failed: ${JSON.stringify(result)}`);
}
console.log(JSON.stringify(result));
