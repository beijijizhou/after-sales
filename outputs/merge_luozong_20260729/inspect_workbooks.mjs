import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const targetPath = "/Users/hongzhonghu/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/a621b502764ff0021710d7999f6e8b00/Message/MessageTemp/f32ee2e158a8b0f3c258a9db25ff72ed/File/新建 XLSX 工作表 (3).xlsx";
const sourcePath = "/Users/hongzhonghu/Library/Containers/com.tencent.xinWeChat/Data/Library/Caches/com.tencent.xinWeChat/2.0b4.0.9/a621b502764ff0021710d7999f6e8b00/SaveTemp/ce67fdf16a8ca9fdfdedaa18a1f2e2f8/罗总 上善若水 丁白娘.xlsx";

for (const [label, path] of [["target", targetPath], ["source", sourcePath]]) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
  const overview = await workbook.inspect({
    kind: "workbook,sheet,table",
    maxChars: 12000,
    tableMaxRows: 20,
    tableMaxCols: 20,
    tableMaxCellChars: 120,
  });
  console.log(`--- ${label} ---`);
  console.log(overview.ndjson);
  const sheets = workbook.worksheets.items;
  for (let index = 0; index < sheets.length; index += 1) {
    const sheet = sheets[index];
    const usedRange = sheet.getUsedRange(true);
    if (!usedRange) {
      continue;
    }
    const preview = await workbook.render({
      sheetName: sheet.name,
      range: usedRange.address,
      scale: 1,
      format: "png",
    });
    await fs.writeFile(
      `${label}-${index + 1}.png`,
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
}
