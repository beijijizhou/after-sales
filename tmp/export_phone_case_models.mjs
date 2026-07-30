import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const repoRoot = "/Users/hongzhonghu/Desktop/after-sales";
const catalogPath = path.join(repoRoot, "assets/dielines/phone_cases/catalog.json");
const outputDir = path.join(
  repoRoot,
  "outputs/019fb135-8a6a-7443-9b28-74cbd56f226b",
);
const outputPath = path.join(outputDir, "手机壳全部刀模型号.xlsx");
const previewPath = path.join(outputDir, "手机壳全部刀模型号_预览.png");

const catalog = JSON.parse(await fs.readFile(catalogPath, "utf8"));
const detailRows = [];
for (const [material, materialInfo] of Object.entries(catalog.materials || {})) {
  for (const [model, modelInfo] of Object.entries(materialInfo.models || {})) {
    const filePath = path.join(
      repoRoot,
      "assets/dielines/phone_cases",
      modelInfo.path,
    );
    detailRows.push([
      material,
      materialInfo.slug || "",
      model,
      (modelInfo.aliases || []).join("、"),
      modelInfo.output_size?.[0] || null,
      modelInfo.output_size?.[1] || null,
      modelInfo.path || "",
      await fs.access(filePath).then(() => "有").catch(() => "缺少"),
    ]);
  }
}
detailRows.sort((a, b) =>
  a[0].localeCompare(b[0], "zh-CN") ||
  a[2].localeCompare(b[2], "en", { numeric: true })
);

const uniqueModels = [...new Set(detailRows.map((row) => row[2]))].sort(
  (a, b) => a.localeCompare(b, "en", { numeric: true }),
);
const materialSummary = Object.entries(catalog.materials || {})
  .map(([material, info]) => [
    material,
    info.slug || "",
    Object.keys(info.models || {}).length,
    (info.aliases || []).join("、"),
  ])
  .sort((a, b) => a[0].localeCompare(b[0], "zh-CN"));

const workbook = Workbook.create();
const summary = workbook.worksheets.add("型号总览");
const details = workbook.worksheets.add("刀模明细");

summary.showGridLines = false;
summary.getRange("A1:D1").merge();
summary.getRange("A1").values = [["手机壳全部刀模型号"]];
summary.getRange("A2:D2").merge();
summary.getRange("A2").values = [[
  "来源：手机壳图片处理刀模目录（assets/dielines/phone_cases/catalog.json）",
]];
summary.getRange("A4:B7").values = [
  ["统计项目", "数量"],
  ["手机壳材质/类型", materialSummary.length],
  ["唯一机型", uniqueModels.length],
  ["刀模组合", detailRows.length],
];
summary.getRange("A9:D9").values = [["手机壳类型", "目录编码", "机型数", "类型别名"]];
if (materialSummary.length) {
  summary.getRangeByIndexes(9, 0, materialSummary.length, 4).values = materialSummary;
}
const modelStart = 11 + materialSummary.length;
summary.getRange(`A${modelStart}:B${modelStart}`).values = [["序号", "唯一机型"]];
summary.getRangeByIndexes(
  modelStart,
  0,
  uniqueModels.length,
  2,
).values = uniqueModels.map((model, index) => [index + 1, model]);

details.showGridLines = false;
details.getRange("A1:H1").merge();
details.getRange("A1").values = [["手机壳刀模组合明细"]];
details.getRange("A3:H3").values = [[
  "手机壳类型", "目录编码", "机型", "机型别名",
  "刀模宽度(px)", "刀模高度(px)", "刀模文件", "文件状态",
]];
details.getRangeByIndexes(3, 0, detailRows.length, 8).values = detailRows;

const titleStyle = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
summary.getRange("A1:D1").format = titleStyle;
details.getRange("A1:H1").format = titleStyle;
summary.getRange("A1:D1").format.rowHeight = 30;
details.getRange("A1:H1").format.rowHeight = 30;
summary.getRange("A2:D2").format = {
  fill: "#DCE6F1",
  font: { color: "#44546A", italic: true },
  horizontalAlignment: "left",
  verticalAlignment: "center",
};

for (const range of [
  summary.getRange("A4:B4"),
  summary.getRange("A9:D9"),
  summary.getRange(`A${modelStart}:B${modelStart}`),
  details.getRange("A3:H3"),
]) {
  range.format = {
    fill: "#4472C4",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#B4C6E7" },
  };
}

summary.getRange("A5:B7").format.borders = {
  preset: "inside",
  style: "thin",
  color: "#D9E2F3",
};
summary.getRange(`A10:D${9 + materialSummary.length}`).format.borders = {
  preset: "inside",
  style: "thin",
  color: "#D9E2F3",
};
summary.getRange(`A${modelStart + 1}:B${modelStart + uniqueModels.length}`).format.borders = {
  preset: "inside",
  style: "thin",
  color: "#E7E6E6",
};
details.getRange(`A4:H${3 + detailRows.length}`).format.borders = {
  preset: "inside",
  style: "thin",
  color: "#E7E6E6",
};
details.getRange(`E4:F${3 + detailRows.length}`).format.numberFormat = "#,##0";
details.getRange(`E4:F${3 + detailRows.length}`).format.horizontalAlignment = "right";

summary.getRange("A1:D7").format.autofitColumns();
summary.getRange(`A9:D${modelStart + uniqueModels.length}`).format.autofitColumns();
details.getRange(`A1:H${3 + detailRows.length}`).format.autofitColumns();
summary.getRange("A:A").format.columnWidth = 20;
summary.getRange("B:B").format.columnWidth = 27;
summary.getRange("D:D").format.columnWidth = 42;
details.getRange("A:A").format.columnWidth = 18;
details.getRange("B:B").format.columnWidth = 22;
details.getRange("C:C").format.columnWidth = 24;
details.getRange("D:D").format.columnWidth = 38;
details.getRange("G:G").format.columnWidth = 42;
summary.freezePanes.freezeRows(9);
details.freezePanes.freezeRows(3);

summary.tables.add(
  `A9:D${9 + materialSummary.length}`,
  true,
  "PhoneCaseMaterialSummary",
);
summary.tables.add(
  `A${modelStart}:B${modelStart + uniqueModels.length}`,
  true,
  "UniquePhoneCaseModels",
);
details.tables.add(
  `A3:H${3 + detailRows.length}`,
  true,
  "PhoneCaseDielineDetails",
);

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
const preview = await workbook.render({
  sheetName: "型号总览",
  range: `A1:D${Math.min(modelStart + uniqueModels.length, 45)}`,
  scale: 1.5,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const check = await workbook.inspect({
  kind: "table",
  range: `型号总览!A1:D${Math.min(modelStart + uniqueModels.length, 45)}`,
  include: "values,formulas",
  tableMaxRows: 45,
  tableMaxCols: 8,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(JSON.stringify({
  outputPath,
  previewPath,
  materialCount: materialSummary.length,
  uniqueModelCount: uniqueModels.length,
  combinationCount: detailRows.length,
  missingFiles: detailRows.filter((row) => row[7] !== "有").length,
  check: check.ndjson,
  errors: errors.ndjson,
}, null, 2));
