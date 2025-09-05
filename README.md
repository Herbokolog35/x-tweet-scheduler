\# X Tweet Scheduler (Python + GitHub Actions)



`data/tweets.txt` içindeki satırları, `data/hours.txt` saat listesine uyarak paylaşır. Zaman dilimi \*\*Europe/Istanbul\*\*.



\## Hızlı Başlangıç

1\) Bu repo dosyalarını oluştur.

2\) GitHub → Settings → Secrets and variables → Actions:

&nbsp;  - TW\_CONSUMER\_KEY

&nbsp;  - TW\_CONSUMER\_SECRET

&nbsp;  - TW\_ACCESS\_TOKEN

&nbsp;  - TW\_ACCESS\_TOKEN\_SECRET

3\) `data/tweets.txt` ve `data/hours.txt` dosyalarını doldur.

4\) Push et. Actions her 5 dakikada bir çalışır; tam dakikada eşleşme varsa sıradaki tweet paylaşılır.



\## Notlar

\- Her satır 1 tweet (280 karakter sınırı).

\- İlerleme `src/state.json` ile izlenir.

\- Test için `DRY\_RUN=true` (Repository → Settings → Actions → Variables → New variable).



