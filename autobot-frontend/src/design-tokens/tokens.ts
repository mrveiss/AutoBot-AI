export const size = ["xs", "sm", "md", "lg", "xl"] as const;
export type Size = typeof size[number];

export const intent = ["error", "warning", "success", "info"] as const;
export type Intent = typeof intent[number];
