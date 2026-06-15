# Questions to check!

## Pipeline

1. prefetxh debug prints - what's happening, why so long? - done
2. run_stage in runner - what the reason for prefetch? - done
3. metric for tuning ????
4. Context length 
Question:
 According to the Chronos-2 model card, the maximum context length is 8192. Inadvertently I've been running longer contexts, without errors or warnings. Is this an actual limit that needs to be respected?

Answer (from creator):
 If your time series are longer than this length, they will be truncated internally to 8192, so you don't need to worry about this. Note that context length here means the length of each unique time series in your dataframe and not the size of the dataframe itself (which can be of any size).

5. Context length / длина датасета. Значения?
6. Tresholds?

7. How dirAcc is calculated?
8. h1+ and h2+ cases - special acc metric
