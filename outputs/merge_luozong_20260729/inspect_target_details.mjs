import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const targetPath = "/Users/hongzhonghu/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/a621b502764ff0021710d7999f6e8b00/Message/MessageTemp/f32ee2e158a8b0f3c258a9db25ff72ed/File/新建 XLSX 工作表 (3).xlsx";
const workbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load(targetPath),
);
for (const kind of ["region", "computedStyle", "formula"]) {
  const result = await workbook.inspect({
    kind,
    sheetId: "Sheet1",
    range: kind === "computedStyle" ? "G1:H9" : "A1:H9",
    maxChars: 10000,
    options: { maxResults: 100 },
  });
  console.log(`--- ${kind} ---`);
  console.log(result.ndjson);
}
