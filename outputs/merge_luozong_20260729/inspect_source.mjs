import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const sourcePath = "/Users/hongzhonghu/Library/Containers/com.tencent.xinWeChat/Data/Library/Caches/com.tencent.xinWeChat/2.0b4.0.9/a621b502764ff0021710d7999f6e8b00/SaveTemp/ce67fdf16a8ca9fdfdedaa18a1f2e2f8/罗总 上善若水 丁白娘.xlsx";
const workbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load(sourcePath),
);
const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 30000,
  tableMaxRows: 100,
  tableMaxCols: 30,
  tableMaxCellChars: 160,
});
console.log(overview.ndjson);
