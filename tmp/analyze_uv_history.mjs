import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [sourcePath, previewPath] = process.argv.slice(2);
const workbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load(sourcePath),
);
const sheet = workbook.worksheets.getItem("Sheet1");
const values = sheet.getRange("A1:AH45").values;
const blocks = [
  { month: 4, headerRow: 1, firstDataRow: 2, lastDataRow: 12, totalRow: 13, days: 30 },
  { month: 5, headerRow: 16, firstDataRow: 17, lastDataRow: 27, totalRow: 28, days: 31 },
  { month: 6, headerRow: 31, firstDataRow: 32, lastDataRow: 43, totalRow: 44, days: 30 },
];

const products = {};
const months = [];
for (const block of blocks) {
  const dayValues = values[block.totalRow].slice(2, 2 + block.days);
  const detailTotal = dayValues.reduce((sum, value) => sum + (Number(value) || 0), 0);
  const statedTotal = Number(values[block.totalRow][33]) || 0;
  months.push({
    month: block.month,
    detailTotal,
    statedTotal,
    difference: detailTotal - statedTotal,
    dailyAverage: detailTotal / block.days,
  });
  for (let row = block.firstDataRow; row <= block.lastDataRow; row += 1) {
    const code = String(values[row][0] || "").trim();
    if (!code) continue;
    const quantity = Number(values[row][33]) || 0;
    products[code] = (products[code] || 0) + quantity;
  }
}

const preview = await workbook.render({
  sheetName: "Sheet1",
  range: "A1:AH45",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({
  months,
  grandTotal: months.reduce((sum, row) => sum + row.detailTotal, 0),
  calendarDays: months.reduce((sum, row) => sum + (row.month === 5 ? 31 : 30), 0),
  dailyAverage: months.reduce((sum, row) => sum + row.detailTotal, 0) / 91,
  products,
}, null, 2));
