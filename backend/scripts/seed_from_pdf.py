"""Seed the database with the 2026-07-15 农业农村日报 (parsed from PDF).
Usage: python -m scripts.seed_from_pdf
Items are pushed through the real ingest service (so dedup is exercised);
then a Daily row is created and a few items are marked 精选.
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal, engine
from app.models import Base, Daily, Item
from app.schemas import IngestItemIn
from app.services import ingest_service

DAILY_DATE = datetime(2026, 7, 15, tzinfo=timezone.utc).date()

HIGHLIGHTS = [
    "《加快农业农村现代化\"十五五\"规划》解读走深：人民日报海外版刊出《\"三农\"补短板，看这4项指标③：3个百分点里的田间\"大智慧\"》，聚焦\"到2030年农业科技进步贡献率达到67%\"硬目标，详解农机装备高质量发展、农业生物制造提升、\"人工智能+农业\"3大行动，明确农业大模型、AI决策系统等未来产业方向。",
    "农业人工智能标准集中\"立柱\"：2026年第二批农业国家和行业标准制修订计划中8项农业人工智能相关行业标准获立项，覆盖农业机器人通用要求、农业农村大模型（术语、参考架构、训练数据质量规范）等领域，构成行业首批农业大模型标准化\"组合拳\"。",
    "农业农村部在哈尔滨召开全国农田建设暨突出问题整治推进会：部署高标准农田建设突出问题整治，强调\"分省分类推进、动真碰硬\"，夯实国家粮食安全根基。",
    "多部门发力夯实农业农村现代化基础：农业农村部、国家林草局、海关总署联合公告优化农作物、林草种质资源出境管理（新规2026-08-01实施）；农业农村部等7部门印发2026年度全国农村公共服务典型案例征集推介工作通知。",
    "农业前沿研究持续上新：Frontiers in Sustainable Food Systems 上线数字农业技术创新与农业绿色全要素生产率、数字经济发展对农业碳排放影响两篇论文；《中国稻米》上线智慧农业技术引领下的水稻生产体系转型等论文。",
]

# (title, url, source_name, published_at, category, tags, summary, is_selected, hotness)
ITEMS = [
    (
        "3个百分点里的田间\"大智慧\"——\"三农\"补短板，看这4项指标③",
        "https://paper.people.com.cn/rmrbhwb/pc/content/202607/15/content_30168774.html",
        "人民日报海外版", "2026-07-15", "报道", ["报道", "十五五", "智慧农业", "农业人工智能"],
        "聚焦《加快农业农村现代化\"十五五\"规划》提出的\"到2030年农业科技进步贡献率达到67%\"（较2025年的64%提升3个百分点）硬指标。详解三大行动：①农机装备高质量发展，针对全国农作物耕种收综合机械化率76.7%、丘陵山区仅53.5%的短板；②农业生物制造提升；③\"人工智能+农业\"，开展农业人工智能应用中试，推动生物育种、生产管理、病虫害监测、产量预测等高质量应用场景落地，推广农业农村领域大模型，培育智慧农（牧、渔）场。南京农业大学仇童伟指出，分子农业与基因编辑育种、农业大模型与AI决策系统是\"未来产业\"方向。",
        True, 90,
    ),
    (
        "农业农村部召开全国农田建设暨突出问题整治推进会",
        "https://szb.farmer.com.cn/nmrb/html/2026-07/15/nw.D110000nmrb_20260715_1-01.htm",
        "农民日报 / 农业农村部", "2026-07-15", "政策", ["政策", "高标准农田", "粮食安全"],
        "会议在哈尔滨召开，部署高标准农田建设突出问题整治，强调\"分省分类推进、动真碰硬\"：治理截留挪用、迟拨滞拨资金和拖欠工程款问题，严厉打击违法招标投标，加快排查整治设施质量问题，健全快速发现处置机制，确保高标准农田\"建好、管护好、使用好\"，为保障国家粮食安全、加快建设农业强国奠定坚实基础。",
        False, 70,
    ),
    (
        "优化农作物、林草种质资源出境管理：农业农村部、国家林草局、海关总署联合发布公告",
        "https://new.qq.com/rain/a/20260715A02AN400",
        "农业农村部 / 国家林草局 / 海关总署", "2026-07-14", "政策", ["政策", "种业振兴", "生物育种", "种质资源"],
        "三部门联合发布公告优化农作物、林草种质资源出境管理，新规将于2026-08-01起施行。公告明确：出境种质资源需提前申办审批文件，规范海关申报填报要求；未获批出境的种质资源将被海关依法扣留处置。此举有利于加强种质资源保护、严控生物育种知识产权与遗传资源外流，支撑种业振兴行动与农业新质生产力培育。",
        False, 60,
    ),
    (
        "8项农业人工智能标准立项获批 智慧农业迎来\"标准时刻\"",
        "https://new.qq.com/rain/a/20260714A07CPB00",
        "农业农村部农业信息化标准化技术委员会", "2026-07-14", "政策", ["政策", "农业人工智能", "行业标准", "农业大模型"],
        "2026年6月，农业农村部下达2026年第二批农业国家和行业标准制修订计划，其中农业信息化标准化技术委员会规划管理的8项农业人工智能相关行业标准成功立项，覆盖农业机器人（通用要求第2部分：作业技术条件）、农业农村大模型（术语、总体参考架构、训练数据质量规范3部分）、作物智能监测等多领域。其中《农业农村大模型》系列标准一次性立项3个部分，是农业行业面向大模型建设的首批标准，将为大模型研发与应用提供体系化结构指引。",
        True, 85,
    ),
    (
        "2026年度济南市数字乡村建设典型案例征集活动公告",
        "https://news.e23.cn/jnnews/2026-07-14/2026071400249.html",
        "济南市委网信办 / 山东山科数字经济研究院", "2026-07-14", "政策", ["政策", "数字乡村", "智慧农业", "山东"],
        "济南市委网信办发布典型案例征集公告，设置两大征集方向：①智慧农业方向（人工智能、物联网、北斗、低空遥感等农业场景应用、智慧农业关键技术攻关与成果转化、农业农村数据共享应用、农民数字素养与技能培训等）；②乡村数字富民产业方向（农产品加工智能化升级、农村电子商务、农文旅融合、农村寄递物流体系、农村数字普惠金融等）。旨在挖掘一批创新性强、落地成效好、可复制可推广的数字乡村示范样板，扎实推进济南市第二批国家数字乡村试点建设。",
        False, 40,
    ),
    (
        "中共辽宁省委、辽宁省人民政府印发《关于锚定农业农村现代化扎实推进乡村全面振兴的实施意见》",
        "https://www.toutiao.com/article/7661891599031140898/",
        "辽宁省委、省政府（农民日报）", "2026-07-13", "政策", ["政策", "乡村振兴", "辽宁", "十五五"],
        "作为\"十五五\"开局之年辽宁\"三农\"工作的纲领性文件，《意见》明确粮食作物播种面积稳定在5330万亩以上等目标，对锚定农业农村现代化、扎实推进乡村全面振兴作出系统部署。",
        False, 45,
    ),
    (
        "川渝数字乡村建设大会在广安召开 发布联合倡议书与机会清单",
        "https://sichuan.scol.com.cn/ggxw/202607/83287214.html",
        "四川在线", "2026-07-13", "报道", ["政策", "数字乡村", "川渝协作", "智慧农业"],
        "以\"数字赋能乡村·协同共创未来\"为主题的大会在四川广安召开，川渝两地8部门联合发布《川渝数字乡村发展联合倡议书》《川渝数字乡村建设机会清单》。倡议书从五大维度提出协同共建：深化党政协同联动、激活市场主体动能、集聚科研智库资源（围绕智慧农机、AI农情监测、农产品溯源联合攻关）、强化舆论宣传赋能、激发基层内生动力。广安区花桥镇万亩智慧粮油基地搭建\"天—空—地\"一体化感知网络、依托\"粮田管家\"平台实现无人作业与产销溯源；龙安柚现代农业园区完成全产业链数字化升级，2025年园区总产值达1.89亿元。",
        False, 65,
    ),
    (
        "多部门发文推进农村客货邮融合发展：打造22万个服务点、2万条线路",
        "https://www.workercn.cn/papers/grrb/2026/07/13/4/news-6.html",
        "工人日报", "2026-07-13", "政策", ["政策", "农村物流", "客货邮融合", "数字基础设施"],
        "交通运输部、公安部、农业农村部、商务部、国家邮政局、中国邮政集团联合印发《农村客货邮融合发展提质增效行动方案（2026—2028年）》。方案提出：到2027年底具备条件的涉农县级行政区农村客货邮融合发展基本实现全覆盖，全国县乡村三级客货邮综合服务站点数量达22万个以上，合作线路达2万条以上；到2028年底东中西部地区农村客货邮服务覆盖建制村比例分别达45%、45%、40%以上。重点任务包括打造集中共配型县级中心、乡镇综合服务站、\"一站式\"村级综合服务点，推广自动化标准化绿色化设备。",
        False, 55,
    ),
    (
        "2026年河南夏粮总产量755.29亿斤 增量全国第一",
        "https://k.sina.com.cn/article_7517400647_1c0126e4705908t6xo.html",
        "河南日报", "2026-07-12", "报道", ["报道", "夏粮", "粮食安全", "卫星遥感", "智慧农业"],
        "2026年河南夏粮总产量755.29亿斤，比上年增加5.28亿斤，同比增长0.7%，增量全国第一。丰收得益于科技增效：针对去年秋汛晚播、苗情偏弱的先天短板，河南实施系统性的\"四补一促\"技术路径，依托卫星遥感等技术实现苗情、墒情、病虫情动态监测与精准预警；深耕深松、水肥一体化等标准化耕作技术全面普及，粮食生产逐步摆脱\"靠天吃饭\"，转向\"靠技增产、靠智增收\"。",
        True, 75,
    ),
    (
        "农业农村部办公厅等7部门联合部署2026年度全国农村公共服务典型案例征集推介工作",
        "https://new.qq.com/rain/a/20260712A05UDH00",
        "农业农村部等7部门", "2026-07-06", "政策", ["政策", "农村公共服务", "数字化", "典型案例"],
        "农业农村部、国家发展改革委、教育部、民政部、文化和旅游部、国家卫生健康委、体育总局七部门联合印发通知，开展2026年度全国农村公共服务典型案例征集推介工作。案例应有效解决农村公共服务领域突出问题，并要求\"提升农村公共服务数字化水平\"，相关场所设施持续开放运行、服务成效显著、可复制可推广。",
        False, 35,
    ),
    # ---------- 学术论文 ----------
    (
        "数字农业技术创新与农业绿色全要素生产率——来自中国县域的证据",
        "https://www.frontiersin.org/journals/sustainable-food-systems/articles/10.3389/fsufs.2026.1898854/full",
        "Frontiers in Sustainable Food Systems", "2026-07-13", "论文", ["论文", "数字农业", "农业绿色发展", "县域面板"],
        "原文标题：Digital Agricultural Technology Innovation and Agricultural Green Total Factor Productivity: County-Level Evidence from China。作者：Ning Qin, Yaping Yang, Pengzhen Liu, Jiayu Chen（暨南大学、衢州学院、浙江农林大学暨阳学院）。摘要（译）：数字农业技术创新（DATI）是农业现代化与绿色转型的重要驱动力。研究基于2014—2021年中国县域平衡面板数据，构建县域DATI测度指标，实证检验DATI对农业绿色全要素生产率（AGTFP）的影响。结果显示：①DATI显著提升AGTFP，但效应因地区、数字基础设施禀赋、农业发展条件而异；②DATI对AGTFP的影响呈显著门槛特征——数字基础设施与财政支农是关键门槛变量；③DATI表现出显著空间依赖性但空间溢出效应有限。",
        False, 50,
    ),
    (
        "数字经济发展对农业碳排放的影响——基于规模效应与效率效应",
        "https://www.frontiersin.org/journals/sustainable-food-systems/articles/10.3389/fsufs.2026.1820332/full",
        "Frontiers in Sustainable Food Systems", "2026-07-10", "论文", ["论文", "数字农业", "农业碳排放", "低碳转型"],
        "原文标题：Impact of Digital Economy Development on Agricultural Carbon Emissions: Evidence from Scale and Efficiency Effects。作者：Zhumei Wang, Qiawen Li, Xiaofu Chen, Fengcun Feng（新疆农业大学、中国农业大学、浙江农林大学）。摘要（译）：基于2011—2022年中国省级面板数据，采用双向固定效应模型分析农业数字化对农业碳排放与碳排放效率的影响。结果显示：农业数字化水平每提升1%，农业碳排放总量下降15.72%、碳排放效率提升3.97%；减排效应主要通过渐进式创新实现；碳减排效应在中国南方与数字发展水平较高的省份更强，并呈现空间溢出效应。",
        False, 50,
    ),
    (
        "数字乡村与农业绿色全要素生产率——基于供给侧与需求侧机制的分析",
        "https://opaj.napstic.cn/periodicalArticle/0120260400927817",
        "国际期刊（外文来源，已译为中文）", "2026-07-10", "论文", ["论文", "数字乡村", "农业绿色发展", "全要素生产率"],
        "原文标题：Digital villages and agricultural green total factor productivity: a supply-side and demand-side mechanism analysis。摘要（译）：研究从供给侧与需求侧双重视角，实证检验数字乡村建设对农业绿色全要素生产率的影响机制，发现数字乡村通过改善要素配置与扩大绿色农产品需求两条路径显著提升农业绿色全要素生产率。",
        False, 45,
    ),
    (
        "智慧农业技术引领下的水稻生产体系转型与多维效益提升路径",
        "https://opaj.napstic.cn/periodicalArticle/0120260400927816",
        "《中国稻米》2026, 32(2): 53-59", "2026-07-13", "论文", ["论文", "智慧农业", "水稻", "农业物联网", "人工智能"],
        "原文标题：Transformation of the Rice Production System and Pathways for Multidimensional Benefit Enhancement Under the Guidance of Smart Agriculture Technology。作者：李彬、张双、杨怡、陈家帅、罗庚（四川航天职业技术学院）。摘要（译）：以黑龙江、江苏、浙江、江西等典型水稻主产区为例，系统分析精准农业、物联网（IoT）、人工智能（AI）等核心智慧技术在水稻全产业链的应用效果。研究表明：上述技术可使农药与化肥施用量减少28%—42%，水分利用效率提升至70%以上，单位面积产量增加13%—16%，整体生产成本下降30%以上。智慧农业技术正成为驱动水稻产业绿色转型的关键路径。",
        True, 70,
    ),
    (
        "基于PQ-ECIES的蔬菜物联网区块链防伪追溯系统",
        "https://www.toutiao.com/article/7660136318680269339",
        "《智慧农业（中英文）》2026, 8(2): 237-250", "2026-07-12", "论文", ["论文", "农业物联网", "区块链溯源", "智慧农业", "后量子密码"],
        "原文标题：Vegetable IoT Blockchain Anti-Counterfeiting Traceability System Based on PQ-ECIES。作者：齐培杨、孙传恒、谭昌伟、王俊、罗娜、邢斌（上海海洋大学、国家农业信息化工程技术研究中心、扬州大学、江苏立卓信息技术有限公司）。摘要（译）：针对蔬菜供应链追溯数据采集准确率低、标签易伪造、数据易篡改等问题，研究集成气象站、农残检测仪、标签打印机等物联网设备，通过硬件标识与企业主体绑定建立\"设备-主体\"可信映射；融合椭圆曲线综合加密方案（ECIES）与后量子密码Kyber算法，研发抗量子混合加密方案，实现物联网数据量子安全加密与全链溯源区块链平台。",
        False, 55,
    ),
    (
        "高时空分辨率遥感支撑的农业精准灾害预警：进展、瓶颈与融合路径",
        "https://doi.org/10.12133/j.smartag.SA202512006",
        "《智慧农业（中英文）》2026, 8(2): 18-34", "2026-07-12", "论文", ["论文", "遥感", "灾害预警", "智慧农业"],
        "原文标题：High Spatiotemporal Resolution Remote Sensing for Precision Agricultural Disaster Early Warning: Progress, Bottlenecks, and Integrative Pathways。作者：许晓斌、朱红春、李峰、贺威、杨家铭、李振海（山东科技大学、山东省气候中心、武汉大学）。摘要（译）：系统综述高时空分辨率遥感在农业精准灾害预警中的研究进展，分析数据获取、模型泛化与地面验证等瓶颈，提出多源遥感与地面物联网融合的预警路径。",
        False, 50,
    ),
    (
        "农业数字化赋能农业绿色发展的效应与机制研究",
        "https://lib.hepec.edu.cn/articlesearch/web_searchingDetail?id=2031644159626",
        "国际期刊（外文来源，已译为中文）", "2026-07-08", "论文", ["论文", "数字化", "农业绿色发展", "农业绿色技术进步"],
        "摘要（译）：基于省级面板数据测算农业数字化水平，实证检验数字化对农业绿色发展的赋能效应及其影响机制。研究发现：①数字化显著促进农业绿色发展，且主要通过推动农业绿色技术进步实现；②数字化通过提高劳动力和土地要素的配置效率赋能农业绿色发展；③赋能效果在东部地区、土地规模化程度和农村人力资本水平较高的省份更强；④赋能效果有赖于数字鸿沟的缩小——跨越数字鸿沟后，数字化表现出更强的促进作用。",
        False, 45,
    ),
    (
        "数字乡村建设对农业碳排放的影响机制与效应研究",
        "https://pssxiv.cn/user/search.htm?field=keywords&value=碳排",
        "ChinaXiv 农林经济管理预印本", "2026-06-30", "论文", ["论文", "数字乡村", "农业碳排放", "门槛回归", "预印本"],
        "作者：朱美峰、李辉、刘婷峰。摘要（译）：基于2010—2023年中国省级面板数据，构建数字乡村评价体系，运用双向固定效应、门槛回归和中介效应模型，系统考察数字乡村驱动农业低碳转型的机制与效应。研究表明：①数字乡村建设对农业碳排放具有显著抑制效应；②该抑制效应呈非线性门槛特征；③数字乡村建设通过促进绿色技术升级，形成\"数字赋能—技术驱动—减排增效\"传导路径。研究为乡村振兴与\"双碳\"目标协同推进提供实证参考与政策启示。",
        False, 40,
    ),
]

DISCLAIMER = (
    "\n\n---\n*本日报内容整理自公开来源，外文资料已译为中文，翻译与摘要仅供参考；"
    "引用与决策请以官方原文与正式出版物为准。*"
)


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        existing = (
            await session.execute(select(Daily).where(Daily.date == DAILY_DATE))
        ).scalar_one_or_none()
        if existing:
            print(f"日报 {DAILY_DATE} 已存在，跳过种子导入")
            return

        item_ids: list[int] = []
        for title, url, source, pub, category, tags, summary, selected, hotness in ITEMS:
            payload = IngestItemIn(
                title=title, url=url, summary=summary, source_name=source,
                published_at=datetime.fromisoformat(pub).replace(tzinfo=timezone.utc),
                category=category, tags=tags,
            )
            result = await ingest_service.ingest_item(session, payload, pushed_by="seed")
            if result.item_id:
                item_ids.append(result.item_id)
                if result.status == "created":
                    item = await session.get(Item, result.item_id)
                    item.is_selected = selected
                    item.hotness = hotness
            print(f"  [{result.status}] {title[:40]}")

        daily = Daily(
            date=DAILY_DATE,
            title=f"农业农村日报 · {DAILY_DATE.isoformat()}",
            highlights=HIGHLIGHTS,
            content=(
                "本期覆盖：农业农村政策与报道 · 农业信息化相关学术论文"
                "（外文来源已译为中文）。" + DISCLAIMER
            ),
            item_ids=item_ids,
        )
        session.add(daily)
        await session.commit()
        print(f"完成：日报 {DAILY_DATE}，共 {len(item_ids)} 条资讯")


if __name__ == "__main__":
    asyncio.run(main())
