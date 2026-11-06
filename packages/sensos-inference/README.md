# sensos-inference

Minimal `InferenceProvider` / `InferenceResult` types and `Llama31MLXProvider`.

* Additive: no existing SensOS module is changed. The `InferenceProvider.generate(prompt, *, max_tokens)`
  contract of the clean-install tree (`~/Projects/sensos`, `sensos/core/inference.py`) is kept; the
  result type has the same field names plus extra fields (token ids, token counts, sampler settings, ...).
* The sampler applies temperature -> top_k -> top_p in the order of Hugging Face transformers 4.48.3
  `generate` (`generation/utils.py` `_get_logits_processor`), with the same warper arithmetic
  (`logits_process.py`: `TemperatureLogitsWarper`, `TopKLogitsWarper`, `TopPLogitsWarper`). The random
  number generator is NumPy's (seeded), not torch's: sampled tokens are not expected to equal HF's for
  the same seed; the *distribution* is the same.
* Tests need no weights: `pytest packages/sensos-inference/tests`.

## Qwen3.5 capture (EXP-WSP-TRAJ001)

`Qwen35MLXCaptureProvider` (`providers/qwen35_mlx_capture.py`) generates with its own MLX loop and returns
`[n_gen, hidden_size]` float32 states at several `CapturePosition`s (`mlp_out`, `block_out` of a decoder layer,
and `final_norm`). The hidden size is read from the model config. `PresencePenaltySampler` applies a vLLM-style
presence penalty. `outcome.py` records "reached max length" and the repetition condition separately, from the
token ids only. `Llama31MLXCaptureProvider` is unchanged. Real-model tests run with
`QWEN35_SNAPSHOT=<snapshot dir> pytest tests/test_qwen35_real_model.py`.
