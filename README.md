# SME Post-check

Rà soát tín dụng sau phê duyệt: lấy lại hồ sơ một khoản đã được duyệt, đối
chiếu với dữ liệu hệ thống, trả lời "ĐVKD có làm đúng không".

Khác dự án `2. SME_creditmemo` ở bản chất bài toán: credit memo **viết báo
cáo**, post-check **chấm luật**. Gần như mọi dòng BRD đều là "so A với B theo
ngưỡng C". Nên ở đây LLM chỉ làm một việc — biến chứng từ thành JSON — còn toàn
bộ 31 tiêu chí là Python thuần.

**Một lần chạy là một hồ sơ.** Không có chế độ chạy theo lô.

## Chạy

```bash
pip install -r requirements.txt
cp .env.example .env          # điền OPENAI_API_KEY, OPENAI_API_BASE, các MODEL_*
nbstripout --install          # một lần mỗi clone: xoá output notebook khi commit
jupyter lab local_postcheck.ipynb
```

Hồ sơ đặt tại `samples/<case_id>/<upload_box>/`, mỗi thư mục con là một hộp
upload có id trong `src/agents/documents/document_matrix.yaml`.

### Hai hồ sơ mẫu

```bash
python3 samples/make_samples.py      # dựng lại từ đầu
```

| Hồ sơ | Nội dung |
|---|---|
| `samples/case_demo` | Hồ sơ B1CP đầy đủ: 11 file, đủ 8 đầu mục bắt buộc, định dạng hợp lệ, **một BCTC XML thuế điện tử thật**, và **một báo cáo CIC dạng scan** |
| `samples/case_nhieu_ky_bctc` | BCTC hai kỳ: 2025 bản scan, 2024 có **cả** bản scan lẫn XML thuế điện tử |
| `samples/case_thieu_ho_so` | Hồ sơ thiếu: vắng 5 đầu mục bắt buộc, một `.csv` và một `.jpg` thay cho chứng từ, thông tin định danh mâu thuẫn |

Toàn bộ là dữ liệu giả định, mỗi file mang dòng đầu ghi rõ điều đó. Hai hồ sơ
này **được commit** (`.gitignore` chỉ loại hồ sơ thật) vì bộ kiểm đọc chúng —
một bản clone mới phải chạy được `run_checks.py` ngay.

BCTC XML là phần đáng giá nhất. `parse_tax_xml` đọc nó tất định, cho ra sáu fact
tài chính thật — kỳ báo cáo, tổng tài sản, tổng nguồn vốn, doanh thu hai kỳ,
LNST — **không gọi LLM lần nào**. Chạy `case_demo` với `Config()` rỗng hoàn toàn
cho ra **3 tiêu chí Đạt bằng số thật**: P03 (định dạng, đọc từ tên file), P06
(tổng tài sản = tổng nguồn vốn) và E05 (biến động doanh thu 12,7%). P07 vẫn
thiếu dữ liệu vì nó cần ngày hạch toán trên T24.

Chạy `case_thieu_ho_so` cho ra P03 **Không đạt** — đúng cái nó sinh ra để chứng
minh.

### BCTC: PDF hay XML đều ra cùng một output

`conform_financial_statement` trong
[financial_statement_extraction.py](src/agents/extraction/financial_statement_extraction.py)
là **chỗ duy nhất** định nghĩa hình dạng đầu ra. Cả đường XML lẫn đường LLM đều
đi qua nó, nên hai đường trả về cùng tập khoá, cùng khối, cùng bố cục cột — kể
cả khối `customer` mà đường XML trước đây không có, khiến hồ sơ chỉ nộp BCTC
dạng XML mất một nguồn đối chiếu tên và mã số thuế cho V01, V02, F01.

**Nhiều kỳ, nhiều định dạng.** Khách có thể nộp 2025 bản scan và 2024 bản XML.
Cả hai đều được xử lý; kỳ báo cáo là **kỳ gần nhất trên toàn hồ sơ**, không phải
kỳ của file đứng đầu bảng chữ cái. Cùng một kỳ mà có hai định dạng thì **bản XML
thắng** — và đó không phải logic dự án này viết: `FinancialRatioCalculator` đã
gộp theo (kỳ, chỉ tiêu) và xếp hạng bằng `SOURCE_RANK` với `xml` trên `llm`.
Việc duy nhất pipeline phải làm là truyền dấu nguồn, thứ nó từng bỏ trống.

Một khác biệt **cố ý giữ**: ô mã chỉ tiêu trên đường XML luôn để trống. Tờ khai
điện tử dùng mẫu B01a-DNN (TT133) đánh số 200/500 cho tổng tài sản/tổng nguồn
vốn, còn bộ khớp chỉ tiêu dùng hệ TT200 với 270/440. Nhét mã vào sẽ khiến 17
metric khớp theo mã sai hệ; đường XML khớp bằng nhãn và cho đúng kết quả.
`verify_financial_contract` chốt lại điều này để không ai lặng lẽ đảo nó.

**Báo cáo CIC là bản scan thuần** — PDF chỉ chứa ảnh, không lớp text — nên nó là
hồ sơ mẫu duy nhất buộc `src/utils/reading/ocr.py` phải chạy. 593 dòng OCR đó
trước nay không bài kiểm nào chạm tới. `verify_samples` khẳng định file này
không có `/Font`, và OCR đọc lại được đúng mã số thuế lẫn cụm
`Ngành nghề hoạt động` — dấu tiếng Việt là thứ OCR sai đầu tiên. Cần `brew install tesseract
tesseract-lang`; thiếu nó thì bài kiểm đỏ kèm hướng dẫn cài.

Ba file `.docx` chỉ đọc được khi đã `pip install python-docx`; chưa cài thì
chúng vẫn nhận diện được theo tên file, chỉ là không có nội dung.

## Kiểm thử

```bash
python3 testing/run_checks.py
```

Hai mươi bài kiểm, chạy trong vài giây, **không gọi LLM và không cần DB thật**.
Làm được vì `Facts` là ranh giới duy nhất giữa phần bẩn (OCR, LLM, SQL) và phần
sạch (bộ luật), nên bộ luật test được từ file JSON. Riêng `verify_dummy_db` chạy
cả phần truy vấn, trên SQLite dựng tại chỗ.

## Kiến trúc

```
đọc hồ sơ  →  trích xuất  →  Facts  →  chấm luật  →  kết xuất
1 case dir     4 pass LLM     78 fact   40 rule       Markdown/PDF/JSON
                              ↑
                    15 tool truy vấn SQL
```

Bảy node LangGraph trong [src/pipeline.py](src/pipeline.py), cùng khuôn với
`supervisor.py` bên CreditMemo: một class `PostcheckSupervisor` giữ config, dựng
đồ thị một lần trong `__init__`, và mỗi bước là một method `_graph_*` nhận state
rồi trả state. `run_postcheck` chỉ khởi động nó và đóng gói kết quả.

Một nhánh thật: **nhận định**. Không cấu hình `commentary_llm` thì đi thẳng sang
kết xuất, thay vì gọi một node để nhận về rỗng và ghi vào nhật ký như thể đã làm
việc gì.

Mỗi node ghi một dòng vào `result.steps`, nên một lượt chạy tự kể lại nó đã làm
gì:

```
1. Đọc 12 tài liệu, 5 chưa đọc được nội dung
2. Trích xuất: 0 lượt gọi mô hình
3. Truy vấn hệ thống: 55 fact có giá trị
4. Lắp fact từ chứng từ: thêm 12 fact
5. Chấm 40 tiêu chí: 30 đạt, 0 không đạt, 10 thiếu dữ liệu
6. Bỏ qua nhận định: chưa cấu hình commentary_llm
7. Kết xuất báo cáo: 13940 ký tự
```

Hai cạnh mang phụ thuộc **hỏng im lặng** nếu đảo: `collect_reference_data` phải
chạy trước `assemble_document_facts` (bộ thu thập ảnh đọc `los.is_site_visit` để
biết "không có ảnh" là câu trả lời hay là lỗ hổng), và `mark_manual_facts` phải
chạy sau cả hai. Đảo lại thì cả hai thứ tự đều chạy trót lọt, chỉ là báo cáo
lặng lẽ ghi "chưa kiểm được" cho một tiêu chí vốn kiểm được.

`verify_graph` chốt điều đó bằng cách dựng đồ thị đảo và chấm lại: nếu đảo mà
chạy ngon và chấm y hệt thì chính bài kiểm đó đang không bảo vệ gì.

Các bước và đồ thị nằm **cùng một file**: đọc từ trên xuống là các bước, rồi tới
`PostcheckSupervisor` khai thứ tự, rồi `run_postcheck` khởi động. Tách đôi từng
buộc hai file phải import lẫn nhau, nên ba lời gọi phải hoãn import vào trong
thân hàm — một cái giá trả cho ranh giới không mang lại gì.

In sơ đồ từ chính đồ thị, không vẽ tay:

```python
from src.pipeline import build_postcheck_graph
print(build_postcheck_graph().get_graph().draw_mermaid())
```

| Tầng | Ở đâu |
|---|---|
| 15 tool truy vấn | [src/tools/](src/tools/) — `los` `cic` `blwl` `amc` `t24` `portfolio` `virac` |
| 4 pass trích xuất (nối dây) | [src/passes.py](src/passes.py) |
| Prompt trích xuất (copy CreditMemo) | [src/agents/extraction/](src/agents/extraction/) |
| Danh mục fact | [src/facts.py](src/facts.py) |
| Cổng thiếu dữ liệu | [src/rules/engine.py](src/rules/engine.py) |
| 40 rule | [src/rules/](src/rules/) — `identity` `fraud` `dossier` `criteria` `operation` `ews` |
| Ngưỡng & checklist | [config/programs.yaml](config/programs.yaml) |
| Khung báo cáo | [src/templates/post-check-template.md](src/templates/post-check-template.md) |
| Bộ đọc template | [src/report/templates.py](src/report/templates.py) |

### Trích xuất dùng lại nguyên của CreditMemo

Ba module trong `src/agents/extraction/` được **copy nguyên vẹn** từ
`2. SME_creditmemo`, không sửa prompt: `financial_statement_extraction`,
`proposal_extraction`, `sitevisit_extraction`. Bộ tài liệu khách hàng gần như
trùng nhau, và chúng đã tinh chỉnh qua nhiều vòng thật. Một rule so sánh chỉ
đúng bằng con số nó được đưa.

Hai pass CIC (`cic_s10a_extraction`, `cic_r20_extraction`) **đã bỏ**: nhóm nợ,
BL/WL và TSBĐ đăng ký tại CIC đều query từ tool ở hai thời điểm — ngày phê duyệt
và ngày rà soát — nên một file trong hồ sơ chỉ mang được một trong hai mốc. Cần
lại thì lấy từ `2. SME_creditmemo/src/agents/extraction/`.

`src/passes.py` là phần **nối dây**, không phải phần trích xuất: pass nào chạy
trên loại tài liệu nào, LLM lấy từ đâu trên `Config`, kết quả ghi vào ô nào của
`PostcheckDocument`, cộng runner và vòng kiểm lúc import.

Ba thứ đến kèm, đáng giá:
- `extract_financial_statement_data` đọc **BCTC XML thẳng bằng `parse_tax_xml`,
  không gọi LLM** — P06 và E05 có số chính xác và miễn phí. Runner gọi pass này
  kể cả khi chưa cấu hình LLM: `ExtractionPass.spends_llm_call` nói pass nào tốn
  tiền cho tài liệu nào, và một pass không tốn gì thì không có lý do để bỏ qua.
- `resolve_report_years` đã xử lý "Số cuối kỳ"/"Kỳ trước"/"122024".
- `FinancialRatioCalculator.match_metric` bóc chỉ tiêu theo mã trước rồi mới
  tới alias đã bỏ dấu, kèm danh sách loại trừ. Bốn khoá cần đã có sẵn.

Số tiền do các pass quy về đồng theo đơn vị từng trang khai; tầng ráp facts đọc
thẳng, **không nhân lại**. Một cái bẫy đáng nhớ: trường R20 tên là
`gia_tri_trieu_vnd` nhưng giá trị trong đó đã là đồng.

**Ba nguồn độc lập về tài sản đảm bảo** giờ đối chiếu chéo được: T24 (ngân hàng
hạch toán gì), Đề nghị vay vốn (khách kê gì), và CIC R20 (đăng ký gì, và đã
giải chấp chưa). O07 bắt trường hợp khoản vay tính là có bảo đảm trong khi trên
CIC không còn tài sản nào đang thế chấp.

### Đưa chứng từ thật vào chạy thử

`.gitignore` chặn `samples/*` và chỉ mở cho ba hồ sơ giả định. Muốn chạy thử với
chứng từ thật thì đặt vào một thư mục **tên bất kỳ khác ba tên đó** — nó tự động
nằm ngoài repo:

```
samples/case_that/ho_so_tai_chinh/bao_cao_tai_chinh_2025.pdf
```

Tên file quyết định đầu mục hồ sơ, nên đặt theo từ khoá trong
`document_matrix.yaml`.

### Database dummy để chạy thử cả phần truy vấn

`samples/dummy_db/make_dummy_db.py` dựng một SQLite đúng hình dạng các view mà
`src/tools/` đang gọi, với hai khách hàng: một khớp hoàn toàn hồ sơ
`samples/case_demo` (chấm ra Đạt) và một lệch ngưỡng ở mọi bảng. Nhờ nó, toàn bộ
luồng — truy vấn, chấm luật, kết xuất — chạy được không cần PROD và không tốn
một call LLM:

```bash
python3 samples/dummy_db/make_dummy_db.py
```

```python
from src.tools._executor import sqlite_executor
Config(query_executor=sqlite_executor("samples/dummy_db/postcheck_dummy.sqlite"))
```

`verify_dummy_db` chấm đúng việc này, bốn điều: 11 câu SQL trong `src/tools/` và
11 bảng trong dataset **phủ nhau hai chiều** (bảng nào không ai select cũng là
lỗi, vì đó là dấu hiệu một tool đã bị xoá mà bảng còn sót), mọi câu chạy được,
mọi fact nguồn hệ thống có giá trị, và các rule đọc chúng ra được kết luận cho cả
hai khách hàng. Tên bảng và tên cột trong đó là **tên tạm**, sẽ đổi cùng lúc với
SQL thật.

### Quy ước ngôn ngữ

Tiếng Anh: biến, hàm, comment, docstring, prompt, **khoá JSON của extraction**,
đường dẫn fact, khoá YAML, giá trị enum. Tiếng Việt: chỉ những chuỗi in ra báo
cáo.

Riêng trong prompt trích xuất, tiếng Việt **bắt buộc phải có ở phần giá trị**: đó
là tiêu đề mà model phải tìm trong chứng từ (`"Số cuối kỳ"`) và nhãn mà schema
phải sinh ra (`"Năm YYYY"`). Dịch chúng sang tiếng Anh là làm hỏng trích xuất trên
một tài liệu viết bằng tiếng Việt. Ranh giới nằm ở **khoá**: khoá đi vào code của
dự án, giá trị thì không.

Khoá được kiểm bằng **một danh sách khai báo** (`EXTRACTION_SCHEMA_KEYS`), không
phải bằng luật chính tả — vì tiếng Việt không dấu (`ten`, `ma_so_thue`,
`dau_hieu`) là ASCII snake_case hợp lệ và lọt qua mọi phép kiểm ký tự. Thứ duy
nhất bắt được nó là một người đọc khoá đó một lần, và việc phải cập nhật danh
sách chính là lúc đó.

Ngoại lệ có
chủ ý là `type_id` trong `document_matrix.yaml`, giữ nguyên để không fork bản
copy. `testing/checks/verify_code_language.py` giữ đường ranh này bằng AST.

## Khung báo cáo nằm trong một file Markdown

[`src/templates/post-check-template.md`](src/templates/post-check-template.md)
quyết định hình dạng báo cáo: tiêu đề, thứ tự mục, tiêu chí nào in dưới mục nào.
Sửa báo cáo là sửa file đó, không đụng Python. Khuôn lấy từ
`financial-analysis-structure.md` của CreditMemo — frontmatter, skeleton
Markdown, `{{Placeholder}}` — cùng bộ đọc `_split_frontmatter` bê từ
`specialist.py`.

**Ai điền phần nào:**

| Phần | Nguồn |
|---|---|
| Khung, tiêu đề, thứ tự mục | template |
| Bảng tiêu chí, tổng hợp, phụ lục | Python, từ `Finding` |
| Hai đoạn Nhận định (2.2 và 2.4) | LLM, theo hướng dẫn nằm cuối template |

Khác CreditMemo ở một điểm có chủ ý: bên đó LLM điền cả skeleton, ở đây ô
`Đạt`/`Không đạt` là đầu ra của 39 rule Python tất định (quyết định D2), nên
Python điền bảng còn LLM chỉ viết hai đoạn nhận định.

Hai thứ template tự chịu trách nhiệm, và có bài kiểm:

- **`<!-- rules: V01 V02 ... -->`** dưới mỗi mục. `verify_template` khẳng định
  mọi rule xuất hiện **đúng một lần** — một rule không có trong template là một
  tiêu chí chấm xong rồi không in ra; một rule xuất hiện hai lần là một kết luận
  bị đếm hai lần trong báo cáo có người ký.
- **Placeholder** — `Template.render` **vỡ** nếu còn `{{...}}` chưa điền, thay vì
  in ra một báo cáo khuyết. Một mục biến mất lặng lẽ thì không ai nhận ra.

### Hai đoạn Nhận định: template nói, code kiểm

Phần sau `<!--GUIDANCE-->` trong template là nội dung ghép vào prompt, không in
ra báo cáo. Nó quy định 2.2 phải nêu gì, và 2.4 phải bám ba căn cứ BRD liệt kê.

Nhưng một dòng trong prompt chỉ là một lời đề nghị. `audit_commentary` kiểm ba
thứ máy kiểm được, và **không sửa văn của mô hình** — vi phạm thì ghi chú ngay
dưới đoạn, vì một đoạn đã được sửa lặng lẽ thì không ai biết mô hình từng viết
sai:

| Kiểm | Vì sao |
|---|---|
| Con số không có trong các finding được đưa vào | Một con số mô hình tự nghĩ ra, nằm cạnh bảng kết luận, sẽ được đọc như số liệu |
| Gán cho một mã tiêu chí kết luận khác với bảng | Bảng kết luận là của hệ thống |
| Có tiêu đề, gạch đầu dòng, hoặc ngoài 3–6 câu | Đây chính là "output thống nhất" |

### Điều đã đánh đổi

Trước đây `src/brd.py` đọc `docs/BRD-post-check.csv` lúc chạy, và ba bài kiểm
chứng minh báo cáo khớp BRD **nguyên văn và đúng thứ tự**. Cơ chế đó đã bỏ để
đổi lấy một file Markdown sửa được. Từ giờ template bám BRD đến đâu là do người
viết template; `docs/BRD-post-check.csv` vẫn nằm đó để đối chiếu bằng mắt. Phần
giữ lại được là khẳng định *không rule nào mồ côi, không rule nào đếm hai lần*.

## Ba trạng thái, không phải hai

`Đạt` · `Không đạt` · **`Thiếu dữ liệu`**

Trạng thái thứ ba là trọng tâm thiết kế. Một bộ luật bỏ qua ô trống sẽ báo xanh
cho chính cái hồi quy vừa làm hỏng khâu thu thập — hồ sơ trông sạch đúng lúc dữ
liệu biến mất.

Nên **runner quyết định thiếu dữ liệu, không phải rule**: `run_rules()` kiểm
`rule.needs` trước, và hàm `check` không bao giờ nhìn thấy một fact rỗng. Chiều
còn lại cũng bị chặn: `Verdict` chỉ nhận `PASS`/`FAIL`, nên một rule không thể
tự tuyên bố là chưa kiểm được để né kết luận.

Cổng này gánh việc thật, đo được: gỡ nó ra rồi gọi thẳng `check` trên hồ sơ đủ
dữ liệu thiếu đúng một fact, **14/84 tổ hợp trả về Đạt** thay vì vỡ — trong đó
C04 và O03 báo "KH và CDN đều không nằm trong BL/WL" khi tra cứu không trả về
gì, và E02 báo tương tự tại thời điểm post-check. 56 crash, 14 trả Không đạt.
Không thể trông vào việc rule tự vỡ.
`testing/checks/verify_missing_data_gate.py` giữ tính chất này.

## Sáu tiêu chí luôn ở trạng thái Thiếu dữ liệu

Không pass nào của CreditMemo đọc được tên, CCCD và năm sinh CDN, chữ ký/con
dấu, chữ ký điện tử trên BCTC, hay ngành nghề trên ĐKKD. Đây là **quyết định có
ý thức**, không phải khuyết tật: bản này không viết pass mới cho chúng.

Sáu fact đó khai tường minh trong `MANUAL_FACTS` (`src/facts.py`) kèm lý do in
ra phụ lục báo cáo, và chặn sáu rule: **V04, V05, V06, V07, P04, P05**.
`verify_manual_facts` chạy hai chiều để con số này không âm thầm trôi.

**Bảy fact đi đường ngược lại**: được thu thập nhưng **không rule nào chấm** —
dư nợ, danh mục tín dụng, giao dịch tài khoản, kế toán trưởng, và ba trường mà
một rule đã thôi đọc. Chúng khai trong `DISPLAY_ONLY_FACTS` vì mặc định của
`verify_needs_paths` là coi "fact không ai đọc" là lỗi, và mặc định đó nên giữ.

Từ khi bỏ mục 1, chúng **cũng không còn được in ra báo cáo** — chỉ còn nằm trong
`result.facts` và file JSON của lượt chạy. Mỗi fact như vậy vẫn tốn một câu truy
vấn mỗi lượt rà soát, nên danh sách này đáng đọc lại mỗi khi nó dài ra.

Riêng Portfolio là **nguồn thứ phát**: nó không giữ bản ghi gốc nào mà được team
portfolio dựng lại từ LOS/T24/CIC. Hai hệ quả mà một hệ thống gốc không có — nó
có thể **trễ** so với T24, và cấu trúc cột là của team portfolio nên có thể **dựng
lại**. Vì vậy rows đi qua nguyên dạng, và chưa rule nào so nó với T24: một tiêu
chí đối chiếu dữ liệu thứ phát với hệ thống gốc phải khai ngưỡng dung sai cho độ
trễ đó trước.

### Bảy nhóm dữ liệu, và vì sao nhãn nguồn phải tách làm hai

Nghiệp vụ đối chiếu giữa **bảy nhóm**: `LOS` · `T24` · `Portfolio` ·
`BL/WL & AMC` · `CIC` · `Virac` · `Chứng từ`. (Nhóm thứ tám, `Hồ sơ`, chỉ chứa
`case.postcheck_date` — tham số của lượt chạy, không phải dữ liệu về khách hàng.)

Mỗi fact trong `FACT_KEYS` mang một `FactSpec` **ba trường**, không phải hai:

```python
class FactSpec(NamedTuple):
    category: str     # một trong bảy nhóm - báo cáo phân loại theo cái này
    delivery: str     # query | dossier | run - ai điền fact
    description: str  # tiếng Việt, in thẳng vào báo cáo
```

Hai trường vì đó là **hai câu hỏi khác nhau**, và chúng tách nhau đúng lúc BCTC
với sitevisit online được xếp vào nhóm chứng từ: chúng là *dữ liệu chứng từ*
(category) nhưng *do truy vấn điền* (delivery). Một cột không nói được cả hai, và
nửa bị mất chính là nửa quyết định fact có bị đánh dấu thiếu khi chạy không có
database — báo cáo sẽ im lặng thay vì nói không tra được.

Đường dẫn fact giữ theo **nơi dữ liệu đến** (`los.financials_online.*`), nhóm hiển
thị theo **dữ liệu đó là gì** (`Chứng từ`). `db_facts()` đọc `delivery`, không đọc
category.

Bốn khẳng định trong `verify_needs_paths` giữ cho bảng phân loại không trôi: mọi
category phải nằm trong danh sách bảy nhóm, mọi delivery phải hợp lệ, **mọi nhóm
phải có ít nhất một fact**, và mỗi dòng trong bảng thu thập của báo cáo phải mang
đúng nhãn của chính các fact nó phủ.

### Bốn loại thông tin trên LOS, bốn tool

LOS không phải một dòng rộng mà là bốn thứ khác hẳn nhau về grain và về mục đích:
**hồ sơ** (phê duyệt, hạn mức, người đại diện, kế toán trưởng), **top 5 cổ đông**,
**khảo sát thực địa RM nhập**, **BCTC RM nhập**.

Hai cái sau quan trọng hơn vẻ ngoài: đó là lời khai của chính RM về cùng những
sự việc mà chứng từ ghi lại, gõ tay vào hệ thống — nên chúng là **nguồn thứ hai
để đối chiếu**, và lệch giữa cái RM gõ với cái giấy tờ nói đúng là loại phát hiện
cuộc rà soát này sinh ra để tìm (V08, V09). Chúng **không** thay thế việc đọc
chứng từ.

Cổ đông là **đối tượng tra cứu riêng**: mỗi người được tra BL/WL, AMC và nhóm nợ
CIC như chính doanh nghiệp và chủ doanh nghiệp (C06 tại thời điểm phê duyệt, E08
tại post-check). Nhóm nợ cổ đông tra theo **CCCD**, không theo MST — mã số thuế
doanh nghiệp không nói gì về lịch sử tín dụng cá nhân.

### Ba danh sách độc lập: BL/WL, AMC, CIC

BL/WL và AMC là **hai danh sách riêng**, không phải hai khung nhìn của BCDE.
AMC là luồng thu hồi nợ: có tên trong đó nghĩa là đối tượng đã vào quy trình xử
lý nợ. Hai danh sách cùng hình dạng, cùng ngữ nghĩa mốc ngày, và cùng đi qua một
hàm khớp `_match_list` trong `src/pipeline.py` — nên chúng luôn so sánh được với
nhau — nhưng là hai bảng, hai fact, hai tool.

AMC tại thời điểm phê duyệt **vào điều kiện tín chấp** (C05, và `unsecured_eligible`
đọc nó), tại post-check thành tiêu chí nhận diện rủi ro sớm (E07). Cổ đông dính
danh sách thì **không** vào `unsecured_eligible`: đó là tín hiệu rủi ro về sở hữu,
còn việc nó có loại doanh nghiệp khỏi tín chấp hay không là câu hỏi chính sách
chưa ai trả lời — trả lời ngầm ở đó sẽ âm thầm làm O03 chặt hơn chương trình quy
định.

### Ảnh khảo sát thực địa: model NHÌN, Python CHẤM

BRD dòng 14 nhắc tới *hình ảnh* khảo sát thực địa. Pass thị giác duy nhất của dự
án ([sitevisit_photo_extraction.py](src/agents/extraction/sitevisit_photo_extraction.py))
**gán nhãn, không phán quyết**: nó nói trong ảnh có gì, còn việc "thế có khớp chân
dung khách hàng không" là hàm thuần đọc `persona_evidence` trong config. Nhờ vậy
V10 vẫn kiểm thử được từ file JSON như 39 tiêu chí kia — không model, không mạng.

Hai ràng buộc đi kèm, và cả hai đều có bài kiểm giữ:

- **Từ vựng đưa cho model là HỢP của mọi chân dung**, không phải danh sách của
  riêng khách hàng này. Đưa đúng danh sách kỳ vọng vào là mời model xác nhận điều
  ta đang muốn nghe.
- **Nhãn ngoài từ vựng bị loại** và ghi vào `extraction_notes`, để một chữ model
  tự nghĩ ra không âm thầm thành bằng chứng một tiêu chí đem đếm.

Cờ `los.is_site_visit` quyết định ảnh có bắt buộc không — đây là lần đầu checklist
có mục **phụ thuộc dữ liệu** (`when: site_visit`) chứ không tĩnh theo chương
trình. Hồ sơ không cần khảo sát thì V10 **Đạt**, không phải Thiếu dữ liệu: dùng
`Facts.set_empty()` để nói "rỗng ở đây là câu trả lời", khác với `[]` mặc định
vốn nghĩa là chưa thu thập được.

**Phần lớn hồ sơ thật gộp ảnh vào một PDF, và mỗi trang thường dán nhiều ảnh** —
nên pass tách tài liệu theo hai cách:

| Trang | Cách xử lý |
|---|---|
| có **≥2 ảnh nhúng** đủ lớn | tách **từng ảnh một**, ở độ phân giải gốc |
| còn lại | render cả trang ở 150 DPI |

Ngưỡng là hai chứ không phải một: một trang scan vốn là *một* ảnh nhúng chiếm trọn
trang, và trang chỉ dán một ảnh thì render cũng cho kết quả tương đương — đồng thời
render còn bắt được thứ vẽ bằng vector chứ không nhúng ảnh. Ảnh nhỏ hơn 200px mỗi
chiều bị loại: đó là logo, đường kẻ, hoặc một mảnh của bản scan bị cắt ô, không
phải ảnh chụp doanh nghiệp.

Tách ảnh không chỉ đúng hơn mà còn **rẻ hơn nhiều**: bốn ảnh tách ra từ một trang
collage nặng 4 KB mỗi ảnh, so với 79 KB nếu render cả trang — và mỗi ảnh giữ
nguyên độ phân giải máy ảnh thay vì còn một phần tư.

Tất cả đi trong **một lượt gọi** cho mỗi tài liệu; nhãn `tên.pdf (trang 2, ảnh 3)`
để người rà soát mở đúng chỗ. `max_photo_images` chặn kích thước payload, ảnh bị
cắt được **ghi vào `extraction_notes`** chứ không biến mất im lặng.

Phần render trang dùng lại `_render_pdf_pages` của `ocr.py` — một định nghĩa duy
nhất cho "trang PDF thành ảnh"; nếu nó bị đổi tên, import nổ lúc nạp module chứ
không âm thầm trả về rỗng.

Ảnh mẫu trong repo là ảnh tổng hợp, không có cảnh thật để model đọc. Chúng chỉ
kiểm phần **xung quanh** pass — nhận diện đầu mục, định dạng, tách trang, nối dây;
chất lượng nhận dạng chỉ đo được khi chạy thật.

**Chưa làm:** xác thực ảnh (chỉnh sửa, chụp lại màn hình, EXIF thời gian và toạ
độ). Đó là chống gian lận, khác hẳn đối chiếu chân dung.

### Chữ ký số: có hay không, chưa phải hợp lệ hay không

`src/utils/reading/digital_signature.py` trả lời **câu hỏi thứ nhất** bằng cách
đọc cấu trúc file: XML có nút `<Signature>` của XMLDSig, PDF có signature
dictionary kèm `/ByteRange`. Không LLM, không thư viện crypto, không mạng — nên
P05 chấm được ngay cả khi chạy hoàn toàn offline.

Hàm trả về **ba trạng thái**, và trạng thái thứ ba là điểm mấu chốt: `None` nghĩa
là *không đọc được định dạng này* (`.docx`, `.xlsx`), khác hẳn `False` là *đã đọc
và không có chữ ký*. Gộp hai thứ đó lại sẽ thành một phát hiện bất lợi cho khách
hàng dựa trên một file chưa ai mở ra.

Điều kiện `/ByteRange` không thừa: một signature dictionary **đã tạo mà chưa ký**
vẫn tự khai `/Type/Sig`, nên nếu chỉ tìm dấu hiệu tên gọi thì ô ký trống sẽ đọc
thành đã ký. `verify_digital_signature` chốt cả hai bẫy này.

Fact này gắn với **loại tài liệu**, không gắn với việc trích xuất có đọc được số
liệu hay không: chữ ký là thuộc tính của file, và một BCTC mà mô hình không phân
tích nổi thì vẫn hoặc đã ký hoặc chưa. Nối theo kết quả trích xuất sẽ khiến một
sự cố LLM trông như một hồ sơ chưa ký.

**Chưa làm:** kiểm tra chữ ký có **hợp lệ** không — đúng chuỗi tin cậy, còn hạn,
nội dung chưa bị sửa sau khi ký. Đó mới là thứ chống giả mạo, và cần thư viện
crypto cùng danh sách CA tin cậy.

### BL/WL là một truy vấn DANH SÁCH

`get_blacklist_watchlist(as_of_date)` trả về **các bản ghi còn hiệu lực tại một
mốc ngày**, không lọc theo khách hàng; việc khớp nằm ở `_match_blwl` trong
`src/pipeline.py`: doanh nghiệp khớp theo MST, chủ doanh nghiệp khớp theo CCCD, và
chỉ khi bản ghi không có MST lẫn CCCD mới khớp theo tên — trùng tên là dương tính
giả mà người rà soát phải tự bác, nên nó là phương án cuối. Nhờ có mốc ngày, C04
(thời điểm phê duyệt) và E02 (post-check) đọc cùng một danh sách mà ra hai kết
luận khác nhau khi bản ghi được thêm vào giữa hai mốc.

Danh sách **rỗng** nghĩa là **không ai bị liệt**, và các đối tượng được coi là
sạch. Đây là lựa chọn của nghiệp vụ, và cái giá của nó cần biết: một lượt tra cứu
hỏng bằng cách trả về 0 dòng — thay vì ném lỗi — sẽ không phân biệt được với một
câu trả lời sạch. Truy vấn ném lỗi thì vẫn báo Thiếu dữ liệu như cũ.
`verify_dummy_db` chốt hành vi này bằng cách xoá sạch hai bảng rồi đòi mọi fact
BL/WL và AMC phải mang giá trị `False`, không phải một lý do.

## Còn phải làm trước khi dùng thật

1. **`pip install -r requirements.txt`** — thiếu `python-docx` thì mọi `.docx`
   trong hồ sơ đọc ra rỗng.
2. **Đấu `query_executor`** — `callable(sql, params) -> list[dict]`. Tên view và
   cột trong `src/tools/` là chỗ cần khớp với hệ thống thật. Mỗi file là một hệ
   thống: `los` (phê duyệt), `bcde` (tra cứu lúc thẩm định), `t24` (core bank:
   hạn mức, TSBĐ, dư nghĩa vụ, giao dịch), `virac` (nguồn bên thứ ba duy nhất). Lưu ý yêu cầu đấu
   nối trong docstring của `get_bcde_blwl`: view phải trả một dòng cho mỗi đối
   tượng kể cả khi sạch, nếu không "không có dòng nào" vừa nghĩa là sạch vừa
   nghĩa là chưa tra được.
3. **Xác nhận ba khoảng trống BRD ở trên** với nghiệp vụ, và duyệt hai dòng
   trong `not_a_check` (dòng 23 và 29 — bước chuẩn bị, không phải tiêu chí chấm).
4. **Điền các TODO trong `config/programs.yaml`** — danh sách mã GSO ngành không
   trọng tâm, `max_pdld_count`, checklist từng chương trình, và bổ sung
   `debt_group_by_label` khi gặp biến thể chữ nhóm nợ mới trên báo cáo CIC.
5. **Nghiệm thu đầu-cuối** trên một hồ sơ thật đã có kết luận post-check thủ
   công. Cần xác nhận riêng rằng `total_capital` vẫn ra được từ bảng cân đối
   thật: prompt BCTC của CreditMemo bỏ dòng không có số (`drop_heading_rows`),
   và nếu dòng "TỔNG CỘNG NGUỒN VỐN" bị coi là heading thì P06 hỏng.
