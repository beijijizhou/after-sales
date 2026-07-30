import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [sourcePath, previewDir] = process.argv.slice(2);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));
const summary = await workbook.inspect({
  kind: "workbook,sheet,table,region",
  maxChars: 18000,
  tableMaxRows: 80,
  tableMaxCols: 30,
  tableMaxCellChars: 100,
});
await fs.mkdir(previewDir, { recursive: true });
const sheets = [];
for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange();
  const address = used?.address || "A1:Z60";
  const preview = await workbook.render({
    sheetName: sheet.name,
    range: address,
    scale: 1,
    format: "png",
  });
  const previewPath = `${previewDir}/${sheet.name.replaceAll("/", "_")}.png`;
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  sheets.push({
    name: sheet.name,
    address,
    values: used?.values,
    formulas: used?.formulas,
    previewPath,
  });
}
console.log(JSON.stringify({ inspect: summary.ndjson, sheets }, null, 2));
