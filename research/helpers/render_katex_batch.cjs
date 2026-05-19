const fs = require('fs');
const katex = require(process.argv[2]);
const formulas = JSON.parse(fs.readFileSync(0, 'utf8'));
const rendered = formulas.map((formula) =>
  katex.renderToString(formula, {
    displayMode: true,
    throwOnError: false,
    output: 'html',
    strict: 'ignore',
    trust: false,
  })
);
process.stdout.write(JSON.stringify(rendered));
