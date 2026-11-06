// Memory-type color palette shared by the graph panel (NVL node colors)
// and the chat panel (memory-layer badges) / legend.

const SHORT_TERM = { fill: '#B2F2BB', stroke: '#2F9E44' }
const LONG_TERM = { fill: '#FFEC99', stroke: '#F08C00' }
const REASONING = { fill: '#D0BFFF', stroke: '#9C36B5' }
const SKILLS = { fill: '#6366F1', stroke: '#4338CA' }
const DEFAULT = { fill: '#A5D8FF', stroke: '#1971C2' }

const LONG_TERM_LABELS = ['Customer', 'Organization', 'Product', 'Plan', 'Feature', 'Incident', 'Preference', 'Fact', 'User']
const SHORT_TERM_LABELS = ['Message', 'Conversation']
const REASONING_LABELS = ['ReasoningTrace', 'ReasoningStep', 'ToolCall', 'Tool', 'AgentStep']

/**
 * Return { fill, stroke } colors for a node based on its Neo4j labels.
 * @param {string[]} labels
 */
export function colorForLabels(labels = []) {
  const safe = Array.isArray(labels) ? labels : []

  if (safe.some((l) => typeof l === 'string' && l.startsWith('Skill'))) {
    return SKILLS
  }
  if (
    safe.some(
      (l) =>
        typeof l === 'string' && (l.startsWith('Entity') || LONG_TERM_LABELS.includes(l)),
    )
  ) {
    return LONG_TERM
  }
  if (safe.some((l) => REASONING_LABELS.includes(l))) {
    return REASONING
  }
  if (safe.some((l) => SHORT_TERM_LABELS.includes(l))) {
    return SHORT_TERM
  }
  return DEFAULT
}

/**
 * Legend data for the graph panel: one colored dot + label per memory layer.
 */
export const LAYER_LABELS = [
  { key: 'short_term', label: 'Short-term memory (Message / Conversation)', ...SHORT_TERM },
  { key: 'long_term', label: 'Long-term memory (Entity: Customer, Product, …)', ...LONG_TERM },
  { key: 'reasoning', label: 'Reasoning memory (Trace / Step / ToolCall)', ...REASONING },
  { key: 'skills', label: 'Skills (Skill / SkillVersion / SkillStep)', ...SKILLS },
  { key: 'other', label: 'Other nodes', ...DEFAULT },
]
