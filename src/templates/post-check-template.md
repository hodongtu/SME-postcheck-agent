---
name: post-check-template
description: Khung báo cáo rà soát tín dụng sau phê duyệt (post-check), bám cấu trúc BRD.
version: 1
---

# BÁO CÁO RÀ SOÁT TÍN DỤNG SAU PHÊ DUYỆT

| Thông tin chung | &nbsp; |
| --- | --- |
| **Khách hàng** | {{TenKhachHang}} |
| **Mã số thuế** | {{MaSoThue}} |
| **Chương trình** | {{ChuongTrinh}} |
| **Ngày rà soát** | {{NgayRaSoat}} |

## Tổng hợp

{{TongHop}}

## 1. Thu thập thông tin/ hồ sơ thực hiện rà soát

### 1.1. Thu thập thông tin/ hồ sơ thực hiện tại thời điểm thẩm định – phê duyệt

{{BangThuThap:1.1}}

### 1.2. Thông tin thu thập nội bộ và bên thứ ba cập nhật đến thời điểm rà soát

{{BangThuThap:1.2}}

## 2. Rà soát tín dụng (Post-check)

### 2.1. Xác thực thông tin

> Kiểm tra tính phù hợp các thông tin Hội sở trả ra về Khách hàng (bao gồm nhưng
> không giới hạn: tên KH, mã số thuế, ngành nghề, thông tin chủ doanh nghiệp
> (nếu có)) so với thông tin trên chứng từ khách hàng cung cấp và thông tin/
> hình ảnh khảo sát thực địa của đơn vị kinh doanh.
>
> Nguồn: Database & Tài liệu upload

<!-- rules: V01 V02 V03 V04 V05 V06 V07 -->
{{BangTieuChi:2.1}}

### 2.2. Nhận diện dấu hiệu nghi ngờ gian lận

> - Kiểm tra tính logic, nhất quán giữa các thông tin khách hàng cung cấp.
> - Kiểm tra tính xác thực của thông tin trên chứng từ do ĐVKD cung cấp theo
>   hướng dẫn của Bộ phận QTRR gian lận.

<!-- rules: F01 F02 -->
{{BangTieuChi:2.2}}

#### Nhận định

{{NhanDinh:2.2}}

### 2.3. Kiểm tra điều kiện chính sách

#### a) Kiểm tra chứng từ có thỏa mãn danh mục hồ sơ theo quy định tại thời điểm cấp tín dụng

> Nguồn: Database & Tài liệu upload

<!-- rules: P01 P02 P03 P04 P05 P06 P07 -->
{{BangTieuChi:2.3.a}}

#### b) Kiểm tra các tiêu chí ĐVKD đã đánh giá tại thời điểm cấp tín dụng có đáp ứng các điều kiện cấp tín dụng của TCB

> Nguồn: Database & Tài liệu upload

<!-- rules: C01 C02 C03 -->
{{BangTieuChi:2.3.b}}

#### c) Kiểm tra các tác nghiệp của ĐVKD đã thực hiện phù hợp với Quy trình cấp tín dụng

> Nguồn: Database

<!-- rules: O01 O02 O03 O04 -->
{{BangTieuChi:2.3.c}}

### 2.4. Đánh giá Nhận diện sớm dấu hiệu rủi ro tín dụng

> Nhận diện sớm dấu hiệu rủi ro tín dụng trên cơ sở ý kiến chuyên gia, căn cứ
> theo các thông tin thu thập nội bộ và bên thứ ba cập nhật đến thời điểm rà
> soát: (i) Giao dịch tài khoản, giao dịch tín dụng tại TCB; (ii) Giao dịch tín
> dụng TCTD; (iii) Thông tin khác (nếu có).

<!-- rules: E01 E02 E03 E04 E05 E06 -->
{{BangTieuChi:2.4}}

#### Nhận định

{{NhanDinh:2.4}}

## 3. Tiêu chí bổ sung ngoài BRD

Những tiêu chí dưới đây không có trong BRD. Chúng dùng dữ liệu đã thu thập cho
các bước trên nên gần như không phát sinh thêm chi phí.

<!-- rules: O05 O06 O07 O08 -->
{{BangTieuChi:EXTRA}}

## Phụ lục: dữ liệu chưa thu thập được

{{PhuLucThieuDuLieu}}

<!--GUIDANCE-->

# Hướng dẫn viết Nhận định

Phần dưới đây KHÔNG in ra báo cáo. Nó được ghép vào prompt của mô hình khi sinh
các khối `{{NhanDinh:...}}` ở trên. Sửa ở đây là đổi cách mô hình viết.

## chung

Bạn là chuyên gia rà soát tín dụng sau phê duyệt tại một ngân hàng Việt Nam.

Bạn nhận một danh sách kết luận rà soát ĐÃ ĐƯỢC QUY TẮC CHỐT. Viết một đoạn văn
xuôi ngắn giúp người đọc thấy bức tranh chung. Đoạn văn này được in vào một báo
cáo tuân thủ, ngay cạnh bảng kết luận mà quy tắc đã quyết định — không điều gì
bạn viết được mâu thuẫn với bảng đó.

BẮT BUỘC
- Viết tiếng Việt, 3–6 câu, văn phong báo cáo nội bộ.
- Một đoạn liền mạch. Không tiêu đề, không gạch đầu dòng, không mở bài.
- Chỉ dùng những con số xuất hiện trong danh sách được đưa.

KHÔNG ĐƯỢC
- Tạo ra kết luận Đạt/Không đạt mới, hay đảo ngược, làm nhẹ đi kết luận đã có.
  Bảng kết luận là của hệ thống, không phải của bạn.
- Bịa số liệu, ngày tháng, tên người hay tên tổ chức.
- Bỏ qua các tiêu chí đang ở trạng thái "Thiếu dữ liệu": đó là việc chưa làm
  xong, không phải việc đã đạt. Nếu có, phải nói rõ.

## 2.2

Trọng tâm: mức độ nhất quán của hồ sơ và những dấu hiệu bất thường máy đã bắt
được.

Phải nêu, theo thứ tự:
1. Hồ sơ có nhất quán không — nếu lệch thì lệch ở trường nào, trên chứng từ nào.
2. Dấu hiệu máy kiểm được: chứng từ đề ngày sau ngày phê duyệt, số hiệu bị dùng
   lại.
3. Giới hạn của kiểm tự động: dấu hiệu chỉnh sửa, con dấu sao chép, phông chữ
   bất thường nằm ngoài phạm vi máy kiểm và cần cán bộ QTRR gian lận xem trực
   tiếp.

## 2.4

Trọng tâm: rủi ro tín dụng nhìn thấy tại thời điểm rà soát, không phải tại thời
điểm phê duyệt.

Phải bám ba căn cứ BRD nêu, mỗi căn cứ ít nhất một ý:
1. Giao dịch tài khoản và giao dịch tín dụng tại TCB — nhóm nợ, BL/WL, số lần
   phát sinh dòng tiền.
2. Giao dịch tín dụng tại các TCTD khác — thông tin CIC tra cứu tại thời điểm
   post-check.
3. Thông tin khác nếu có — chênh lệch doanh thu giữa các nguồn, biến động doanh
   thu giữa hai kỳ.

Nếu một căn cứ không có dữ liệu, nói rõ là chưa tra cứu được chứ không bỏ qua.
