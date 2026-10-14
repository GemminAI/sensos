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
