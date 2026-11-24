# 廃止：旧 段階2B NLP専用DB構築・PoCデータ移行 指示書

**この指示書は2026-11-24に全面改訂され、実行禁止となりました。**

現行の段階2B指示書は [2026-11-24_nlp_db_build_instruction.md](2026-11-24_nlp_db_build_instruction.md) です。必ずそちらを使用してください。

変更点: 8テーブルの簡素なDB、PostgreSQL 16 + pgvector、LLMによる収集・索引付けの一体化、Embedding処理の独立、情報不足を許容、SQLのみでの抽出。旧PoC 24件の移行は行いません。旧スキーマ・旧移行条件を実装しないでください。

旧版はGit履歴（[814d514](https://github.com/kendo910x/keibaAI_nlp/blob/814d5144e495c72e6e1cc5e01498861338a4b064/docs/instructions/2026-11/2026-11-22_nlp_db_and_poc_migration_instruction.md)）に保全されています。
