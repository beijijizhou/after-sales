import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const sourcePath = process.argv[2];
const previewDir = process.argv[3];
const workbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load(sourcePath),
);
const sheets = workbook.worksheets.items;
const results = [];
await fs.mkdir(previewDir, { recursive: true });

for (let index = 0; index < sheets.length; index += 1) {
  const sheet = sheets[index];
  const used = sheet.getUsedRange();
  const address = used?.address || "A1:A1";
  const inspection = await workbook.inspect({
    kind: "table",
    range: `${sheet.name}!${address}`,
    include: "values,formulas",
    tableMaxRows: 120,
    tableMaxCols: 30,
    maxChars: 30000,
  });
  const preview = await workbook.render({
    sheetName: sheet.name,
    range: address,
    scale: 1,
    format: "png",
  });
  const previewPath = `${previewDir}/sheet_${index + 1}.png`;
  await fs.writeFile(
    previewPath,
    new Uint8Array(await preview.arrayBuffer()),
  );
  results.push({
    sheet: sheet.name,
    address,
    inspection: inspection.ndjson,
    previewPath,
  });
}

console.log(JSON.stringify(results, null, 2));
