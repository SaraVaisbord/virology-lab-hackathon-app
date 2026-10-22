// DEVELOPMENT ONLY — invented numbers in the exact shape of GET /insights/corrections, to check the dashboard's
// layout before real corrections exist. Loaded only when import.meta.env.DEV (see useCorrectionInsights), so it is
// not in a production build, and the dashboard marks it as sample data. Holds no patient data.
export const CORRECTION_INSIGHTS_SAMPLE = {
  status: 'ok',
  message: null,
  since: null,
  until: null,
  field_name: null,
  coverage: {
    reviewed_fields: 412,
    corrected_fields: 57,
    required_reviewed_fields: 20,
    auto_accepted_fields: 96,
    by_field: [
      { field_name: 'commitment_number', reviewed: 74, corrected: 23 },
      { field_name: 'received_date', reviewed: 61, corrected: 14 },
      { field_name: 'central_number', reviewed: 70, corrected: 9 },
      { field_name: 'id_number', reviewed: 59, corrected: 6 },
      { field_name: 'sender', reviewed: 52, corrected: 3 },
      { field_name: 'last_name', reviewed: 48, corrected: 2 },
      { field_name: 'first_name', reviewed: 48, corrected: 0 },
    ],
  },
  insights: [
    {
      pattern_type: 'wrong_field', field_name: 'commitment_number', matched_field: 'central_number', digit_swap: null, source: null,
      event_count: 12, reviewed_count: 74, share: 0.162, first_seen: '2026-09-24T07:12:00', last_seen: '2026-10-21T13:40:00',
      concentrated_in: { form_type: 'leumit', sender: 'לאומית', written_as: null }, support: 'medium',
      recommendation: 'ערך שהוצג בשדה מספר התחייבות היה שייך למספר מרכזי – מומלץ לחדד בהנחיה ל-AI את ההבחנה בין שני השדות',
    },
    {
      pattern_type: 'frequent_correction', field_name: 'commitment_number', matched_field: null, digit_swap: null, source: null,
      event_count: 23, reviewed_count: 74, share: 0.311, first_seen: '2026-09-23T08:01:00', last_seen: '2026-10-21T13:40:00',
      concentrated_in: { form_type: null, sender: null, written_as: null }, support: 'medium',
      recommendation: '31% מהערכים שנבדקו בשדה מספר התחייבות תוקנו – מומלץ לבדוק את ההנחיה ל-AI ואת דוגמאות הטפסים לשדה זה',
    },
    {
      pattern_type: 'day_month_swap', field_name: 'received_date', matched_field: null, digit_swap: null, source: null,
      event_count: 11, reviewed_count: 61, share: 0.18, first_seen: '2026-10-02T09:30:00', last_seen: '2026-10-20T11:05:00',
      concentrated_in: { form_type: 'hospital', sender: null, written_as: 'handwritten' }, support: 'medium',
      recommendation: 'בשדה תאריך קבלה היום והחודש הוחלפו – מומלץ לבדוק את פורמט התאריך בהנחיה ל-AI',
    },
    {
      pattern_type: 'digit_confusion', field_name: 'central_number', matched_field: null, digit_swap: '1>7', source: null,
      event_count: 4, reviewed_count: 70, share: 0.057, first_seen: '2026-10-11T10:15:00', last_seen: '2026-10-19T14:22:00',
      concentrated_in: { form_type: null, sender: null, written_as: 'handwritten' }, support: 'low',
      recommendation: 'בשדה מספר מרכזי הספרה 7 נקראה שוב ושוב כ-1 – מומלץ לבדוק את איכות הסריקה ואת קריאת הספרות האלה',
    },
    {
      pattern_type: 'silent_error', field_name: 'id_number', matched_field: null, digit_swap: null, source: null,
      event_count: 3, reviewed_count: 59, share: 0.051, first_seen: '2026-10-14T08:40:00', last_seen: '2026-10-14T12:10:00',
      concentrated_in: { form_type: 'clalit', sender: 'כללית', written_as: null }, support: 'low',
      recommendation: "ערכים בשדה ת\"ז סומנו 'אומת משני מקורות' ובכל זאת תוקנו – מומלץ לבדוק את כללי האימות של השדה לפני שסומכים על הסימון",
    },
  ],
}
