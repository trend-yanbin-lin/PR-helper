🎬 YouTube 影音下載與分類專案
====================

這是一個以 Python 撰寫的專案，**下載 YouTube 視頻與音訊並進行分類整理**。核心流程大致如下：
1.  使用 **youtube_dl** 下載影音檔案，並取得其 metadata
2.  利用 **sortedcollections** 建立高效資料結構，以便分類、索引與查詢

🚀 功能簡介
-------

*   從 YouTube（或其他支援的網站）批次下載影片或播放清單
*   取得影片標題、頻道名稱、時長、格式等 metadata
*   將不同分類（例如日期、頻道、標籤）整理為索引資料結構，支援快速查詢與排序
*   採用高效容器管理，例如依不同條件分類後可快速篩選或統計


🧰 使用到的套件
-----------

### **youtube_dl**

*   採用 Python 實作，支援 Windows、macOS、Linux，授權為 Unlicense（public domain
*   提供豐富 CLI 選項、格式選擇、批次處理、多平台支援
    

### **sortedcollections**

*   提供一系列排序資料結構，例如：
    *   `ValueSortedDict`（依 value 排序的 dict）
    *   `ItemSortedDict`（支持 key 函數排序）
    *   `NearestDict`（支援最近 key 查找）
    *   `OrderedDict/Set` 和 `IndexableDict/Set`（可透過數字索引訪問）
    *   `SegmentList`（支援快速隨機插入與刪除）
*   純 Python 實現，無需 C 扩展，擁有高效性能
