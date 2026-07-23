from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd

from automation.api.diy19 import DIY19_BASE_URLS
from automation.production import (
    DTF_PRODUCTION_PLATFORMS,
    SDS_PLATFORM_PROFILES,
    ProductionDataResult,
    load_production_data,
)


ALL_CLOTHING_PLATFORMS = "全部衣服平台"
CLOTHING_CATEGORIES = {"黑白短袖", "彩色短袖", "卫衣"}
API_PLATFORMS = {
    "汉森", "方果", *DIY19_BASE_URLS, *SDS_PLATFORM_PROFILES,
}


@dataclass(frozen=True)
class BatchProductionResult:
    data: pd.DataFrame
    platform_results: dict
    errors: dict


def load_all_clothing_production(
    start_date,
    end_date,
    credentials_by_platform,
    initial_errors=None,
    report_progress=None,
    start_hour=0,
    end_hour=23,
    platforms=None,
    existing_results=None,
):
    report = report_progress or (lambda _message: None)
    errors = dict(initial_errors or {})
    results = dict(existing_results or {})
    requested = tuple(platforms or DTF_PRODUCTION_PLATFORMS)
    browser_platforms = [
        platform for platform in requested
        if platform not in API_PLATFORMS and platform not in errors
    ]
    report("第一阶段：优先读取蜂鸟 ERP 和 S2B 浏览器平台")
    for index, platform in enumerate(browser_platforms, start=1):
        report(f"浏览器平台 {index}/{len(browser_platforms)}：{platform}")
        try:
            results[platform] = _load_browser_platform(
                platform, start_date, end_date, start_hour, end_hour, report
            )
        except Exception as error:
            errors[platform] = str(error)
            report(f"{platform} 获取失败，继续读取其他平台")

    api_platforms = [
        platform for platform in requested
        if platform in API_PLATFORMS and platform not in errors
    ]
    report(f"第二阶段：并行读取 {len(api_platforms)} 个 API 平台")
    with ThreadPoolExecutor(
        max_workers=max(1, min(6, len(api_platforms)))
    ) as executor:
        futures = {
            executor.submit(
                load_production_data,
                platform,
                start_date,
                end_date,
                credentials=credentials_by_platform.get(platform),
                start_hour=start_hour,
                end_hour=end_hour,
            ): platform
            for platform in api_platforms
        }
        for future in as_completed(futures):
            platform = futures[future]
            try:
                results[platform] = future.result()
                report(f"{platform} 获取完成")
            except Exception as error:
                errors[platform] = str(error)
                report(f"{platform} 获取失败，继续读取其他平台")

    retry_platforms = [
        platform for platform in browser_platforms if platform in errors
    ]
    if retry_platforms:
        report(
            "第三阶段：仅重试失败的浏览器平台："
            + "、".join(retry_platforms)
        )
    for index, platform in enumerate(retry_platforms, start=1):
        report(f"重试 {index}/{len(retry_platforms)}：{platform}")
        try:
            results[platform] = _load_browser_platform(
                platform, start_date, end_date, start_hour, end_hour, report
            )
            errors.pop(platform, None)
            report(f"{platform} 重试成功")
        except Exception as error:
            errors[platform] = str(error)
            report(f"{platform} 重试仍失败，已停止继续请求")

    frames = [_clothing_rows(result.data) for result in results.values()]
    frames = [frame for frame in frames if not frame.empty]
    if not results:
        raise ValueError("所有平台均获取失败，请检查登录状态和平台凭据")
    combined = pd.concat(frames, ignore_index=True) if frames else _empty_frame()
    return BatchProductionResult(combined, results, errors)


def _load_browser_platform(
    platform, start_date, end_date, start_hour, end_hour, report
):
    return load_production_data(
        platform,
        start_date,
        end_date,
        report_progress=lambda message: report(f"{platform}：{message}"),
        start_hour=start_hour,
        end_hour=end_hour,
    )


def _clothing_rows(df):
    return df.loc[
        df["部门"].eq("DTF") & df["品类"].isin(CLOTHING_CATEGORIES)
    ].copy()


def _empty_frame():
    return pd.DataFrame(columns=[
        "生产项编码", "生产单号", "部门", "品类", "材质", "颜色",
        "尺码", "型号", "数量", "生产项状态", "运营商", "创建时间",
        "生产完成时间",
    ])
