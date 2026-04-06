WITH filtered AS (
  SELECT
    DATE,
    DATE(PARSE_TIMESTAMP('%Y%m%d%H%M%S', CAST(DATE AS STRING))) AS article_day,
    SourceCommonName,
    DocumentIdentifier AS url,
    V2Organizations,
    V2Themes,
    TranslationInfo
  FROM
    `gdelt-bq.gdeltv2.gkg_partitioned`
  WHERE
    DATE(_PARTITIONTIME) BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND CURRENT_DATE()
    AND (
      TranslationInfo IS NULL
      OR REGEXP_CONTAINS(TranslationInfo, r'(^|;)srclc:eng(;|$)')
    )
    AND (
      REGEXP_CONTAINS(LOWER(V2Organizations), r'(^|;)nvidia,')
      OR REGEXP_CONTAINS(LOWER(V2Organizations), r'(^|;)intel,')
      OR REGEXP_CONTAINS(LOWER(V2Organizations), r'(^|;)qualcomm,')
      OR REGEXP_CONTAINS(LOWER(V2Organizations), r'(^|;)broadcom,')
      OR LOWER(V2Themes) LIKE '%semiconductor%'
      OR LOWER(V2Themes) LIKE '%gpu%'
      OR LOWER(V2Themes) LIKE '%chip%'
    )
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY article_day
      ORDER BY RAND()
    ) AS rn
  FROM filtered
)
SELECT
  DATE,
  SourceCommonName,
  url,
  V2Organizations,
  V2Themes,
  TranslationInfo
FROM ranked
WHERE rn <= 100
ORDER BY article_day DESC, rn;