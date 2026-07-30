import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const targetPath = "/Users/hongzhonghu/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/a621b502764ff0021710d7999f6e8b00/Message/MessageTemp/f32ee2e158a8b0f3c258a9db25ff72ed/File/新建 XLSX 工作表 (3).xlsx";
const outputPath = "新建 XLSX 工作表 (3)_已填罗总价格.xlsx";

const workbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load(targetPath),
);
const summary = workbook.worksheets.getItem("Sheet1");
const basis = workbook.worksheets.getItem("Sheet2");

basis.getRange("A1:G1").merge();
basis.getRange("A1").values = [["罗总价格计算依据"]];
basis.getRange("A2:G8").values = [
  ["款号", "适用尺码", "原衣价格", "1图价格", "2图价格", "单面", "双面"],
  ["180TSH", "S-3XL", 22, 1, 3, null, null],
  ["180TSH", "4XL-5XL", 24, 1, 3, null, null],
  ["TSH", "S-3XL", 16.5, 1, 3, null, null],
  ["TSH", "4XL-5XL", 19.5, 1, 3, null, null],
  ["CVC", "S-3XL", 14, 1, 3, null, null],
  ["CVC", "4XL-5XL", 16, 1, 3, null, null],
];
basis.getRange("F3").formulas = [["=C3+D3"]];
basis.getRange("F3:F8").fillDown();
basis.getRange("G3").formulas = [["=C3+E3"]];
basis.getRange("G3:G8").fillDown();
basis.getRange("A1:G1").format = {
  fill: "#315B45",
  font: { bold: true, color: "#FFFFFF", fontSize: 14 },
  horizontalAlignment: "center",
};
basis.getRange("A2:G2").format = {
  fill: "#DCE9E1",
  font: { bold: true, color: "#1F2937" },
  horizontalAlignment: "center",
  borders: { preset: "all", style: "thin", color: "#B8C7BD" },
};
basis.getRange("A3:G8").format.borders = {
  preset: "all",
  style: "thin",
  color: "#D8E0DB",
};
basis.getRange("B3:B8").format.horizontalAlignment = "center";
basis.getRange("C3:G8").format.numberFormat = "0.00";
basis.getRange("A1:G8").format.autofitColumns();
basis.getRange("A1:G8").format.autofitRows();
basis.freezePanes.freezeRows(2);
basis.showGridLines = false;

summary.getRange("G2:H9").copyFrom(summary.getRange("D2:E9"), "all");
summary.getRange("G2:H9").formulas = [
  ["='Sheet2'!F3", "='Sheet2'!G3"],
  ["='Sheet2'!F4", "='Sheet2'!G4"],
  ["='Sheet2'!F3", "='Sheet2'!G3"],
  ["='Sheet2'!F4", "='Sheet2'!G4"],
  ["='Sheet2'!F5", "='Sheet2'!G5"],
  ["='Sheet2'!F6", "='Sheet2'!G6"],
  ["='Sheet2'!F7", "='Sheet2'!G7"],
  ["='Sheet2'!F8", "='Sheet2'!G8"],
];
summary.getRange("G2:H9").format.numberFormat = "0.00";
summary.getRange("G2:H9").format.horizontalAlignment = "center";

const inspection = await workbook.inspect({
  kind: "table",
  range: "Sheet1!A1:H9",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 10,
  maxChars: 10000,
});
console.log(inspection.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

for (const [sheetName, range, fileName] of [
  ["Sheet1", "A1:H9", "final-main-preview.png"],
  ["Sheet2", "A1:G8", "final-basis-preview.png"],
]) {
  try {
    const preview = await workbook.render({
      sheetName,
      range,
      scale: 1.5,
      format: "png",
    });
    await fs.writeFile(
      fileName,
      new Uint8Array(await preview.arrayBuffer()),
    );
  } catch (error) {
    console.warn(`${sheetName} preview unavailable: ${error.message}`);
  }
}
