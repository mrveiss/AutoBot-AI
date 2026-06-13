# Handoff: issue-9980
status: complete
pr: #10077
base_at_push: origin/Dev_new_gui (rebased at push)
gates: enum-values-test=PASS(13) ruff=PASS create_all-parity=PASS(disposable-pg16)
needs_rebase_before_merge: no
remaining: (none)
notes: |
  values_callable=pg_enum_values on all 11 LLC sa.Enum(PyEnum) columns + llc/models/enums.py helper.
  Verified: create_all over Base.metadata passes the old #9980 abort (llc_approvals); 7 migration-backed
  enum types match migration labels exactly. Regression test auto-discovers all LLC PyEnum columns.
  Residual drift filed (out of scope): #10043 (no migration for work_products/work_item_relations),
  #10075 (dup ix_llc_secrets_company_id), #10076 (membershiprole label ORDER drift).
worktree: .worktrees/issue-9980 (safe to remove after merge)
