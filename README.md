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
không có `/Font`, và OCR đọc lại được đúng mã số thuế lẫn cụm `Nợ đủ tiêu chuẩn`
— dấu tiếng Việt là thứ OCR sai đầu tiên. Cần `brew install tesseract
tesseract-lang`; thiếu nó thì bài kiểm đỏ kèm hướng dẫn cài.

Bảy file `.docx` chỉ đọc được khi đã `pip install python-docx`; chưa cài thì
chúng vẫn nhận diện được theo tên file, chỉ là không có nội dung.

## Kiểm thử

```bash
python3 testing/run_checks.py
```

Mười chín bài kiểm, chạy trong vài giây, **không gọi LLM và không cần DB**. Làm
được vì `Facts` là ranh giới duy nhất giữa phần bẩn (OCR, LLM, SQL) và phần sạch
(bộ luật), nên bộ luật test được từ file JSON.

## Kiến trúc

```
đọc hồ sơ  →  trích xuất  →  Facts  →  chấm luật  →  kết xuất
1 case dir     5 pass LLM     55 fact   33 rule       Markdown/PDF/JSON
                              ↑
                     7 tool truy vấn SQL
```

Năm bước gọi tuần tự trong `src/pipeline.py`. Không LangGraph: credit memo cần
graph vì có bốn nhánh agent, post-check chỉ có một đường chạy.

| Tầng | Ở đâu |
|---|---|
| 7 tool truy vấn | [src/tools/](src/tools/) — `bep` `bcde` `t24` `virac` |
| 5 pass trích xuất (nối dây) | [src/passes.py](src/passes.py) |
| Prompt trích xuất (copy CreditMemo) | [src/agents/extraction/](src/agents/extraction/) |
| Danh mục fact | [src/facts.py](src/facts.py) |
| Cổng thiếu dữ liệu | [src/rules/engine.py](src/rules/engine.py) |
| 33 rule | [src/rules/](src/rules/) — `identity` `fraud` `dossier` `criteria` `operation` `ews` |
| Ngưỡng & checklist | [config/programs.yaml](config/programs.yaml) |
| Khung báo cáo | [src/templates/post-check-template.md](src/templates/post-check-template.md) |
| Bộ đọc template | [src/report/templates.py](src/report/templates.py) |

### Trích xuất dùng lại nguyên của CreditMemo

Năm module trong `src/agents/extraction/` được **copy nguyên vẹn** từ
`2. SME_creditmemo`, không sửa prompt: `financial_statement_extraction`,
`proposal_extraction`, `sitevisit_extraction`, `cic_s10a_extraction`,
`cic_r20_extraction`. Bộ tài liệu khách hàng gần như trùng nhau, và chúng đã
tinh chỉnh qua nhiều vòng thật. Một rule so sánh chỉ đúng bằng con số nó được
đưa.

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
samples/case_that/ho_so_noi_bo/thong_tin_cic_cua_khach_hang_vay.pdf
```

Tên file quyết định đầu mục hồ sơ, nên đặt theo từ khoá trong
`document_matrix.yaml`. Mã biểu mẫu cũng nhận được: `CIC_S10A.pdf` vào pass
S10A, `CIC_R20.pdf` vào pass R20.

### Quy ước ngôn ngữ

Tiếng Anh: biến, hàm, comment, docstring, prompt, khoá JSON, đường dẫn fact,
khoá YAML, giá trị enum. Tiếng Việt: chỉ những chuỗi in ra báo cáo. Ngoại lệ có
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
`Đạt`/`Không đạt` là đầu ra của 33 rule Python tất định (quyết định D2), nên
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
C03 và O03 báo "KH và CDN đều không nằm trong BL/WL" khi tra cứu không trả về
gì, và E02 báo tương tự tại thời điểm post-check. 56 crash, 14 trả Không đạt.
Không thể trông vào việc rule tự vỡ.
`testing/checks/verify_missing_data_gate.py` giữ tính chất này.

## Bảy tiêu chí luôn ở trạng thái Thiếu dữ liệu

Không pass nào của CreditMemo đọc được CCCD và năm sinh CDN, chữ ký/con dấu,
chữ ký điện tử trên BCTC, số hiệu chứng từ, ngành nghề trên ĐKKD, hay file
BL/WL tra cứu tại thời điểm post-check. Đây là **quyết định có ý thức**, không
phải khuyết tật: bản này không viết pass mới cho chúng.

Tám fact đó khai tường minh trong `MANUAL_FACTS` (`src/facts.py`) kèm lý do in
ra phụ lục báo cáo, và chặn bảy rule: **V05, V06, V07, F02, P04, P05, E02**.
`verify_manual_facts` chạy hai chiều để con số này không âm thầm trôi.

## Còn phải làm trước khi dùng thật

1. **`pip install -r requirements.txt`** — thiếu `python-docx` thì mọi `.docx`
   trong hồ sơ đọc ra rỗng.
2. **Đấu `query_executor`** — `callable(sql, params) -> list[dict]`. Tên view và
   cột trong `src/tools/` là chỗ cần khớp với hệ thống thật. Mỗi file là một hệ
   thống: `bep` (phê duyệt), `bcde` (tra cứu lúc thẩm định), `t24` (core bank:
   hạn mức, TSBĐ, dư nghĩa vụ, giao dịch), `virac` (nguồn bên thứ ba duy nhất). Lưu ý yêu cầu đấu
   nối trong docstring của `get_bcde_blwl`: view phải trả một dòng cho mỗi đối
   tượng kể cả khi sạch, nếu không "không có dòng nào" vừa nghĩa là sạch vừa
   nghĩa là chưa tra được.
3. **Xác nhận ba khoảng trống BRD ở trên** với nghiệp vụ, và duyệt hai dòng
   trong `not_a_check` (dòng 23 và 29 — bước chuẩn bị, không phải tiêu chí chấm).
4. **Điền các TODO trong `config/programs.yaml`** — danh sách mã GSO ngành không
   trọng tâm, `min_pdld_count`, checklist từng chương trình, và bổ sung
   `debt_group_by_label` khi gặp biến thể chữ nhóm nợ mới trên báo cáo CIC.
5. **Nghiệm thu đầu-cuối** trên một hồ sơ thật đã có kết luận post-check thủ
   công. Cần xác nhận riêng rằng `total_capital` vẫn ra được từ bảng cân đối
   thật: prompt BCTC của CreditMemo bỏ dòng không có số (`drop_heading_rows`),
   và nếu dòng "TỔNG CỘNG NGUỒN VỐN" bị coi là heading thì P06 hỏng.
