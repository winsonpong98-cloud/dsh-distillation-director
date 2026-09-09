import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const PLUGIN_NAME = 'dsh-distillation-director'
const SKILL_URL = new URL('./SKILL.md', import.meta.url)
const RESOURCE_DIRECTORY_URL = new URL('./', import.meta.url)

function unquoteYamlScalar(value) {
  const trimmed = value.trim()
  const first = trimmed.at(0)
  const last = trimmed.at(-1)

  if (trimmed.length >= 2 && first === last && (first === '"' || first === "'")) {
    return trimmed.slice(1, -1)
  }

  return trimmed
}

export function parseSkillMarkdown(markdown) {
  const match = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)([\s\S]*)$/)
  if (!match) {
    throw new Error('SKILL.md must begin with YAML frontmatter')
  }

  const [, frontmatter, content] = match
  const nameMatch = frontmatter.match(/^name:\s*(.+)$/m)
  const descriptionMatch = frontmatter.match(/^description:\s*(.+)$/m)

  if (!nameMatch || !descriptionMatch) {
    throw new Error('SKILL.md frontmatter must contain name and description')
  }

  const skillName = unquoteYamlScalar(nameMatch[1])
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(skillName)) {
    throw new Error(`Invalid DSH skill name: ${skillName}`)
  }

  return {
    name: skillName,
    description: unquoteYamlScalar(descriptionMatch[1]),
    content,
  }
}

const parsedSkill = parseSkillMarkdown(readFileSync(SKILL_URL, 'utf8'))

export const name = PLUGIN_NAME
export const inject = ['skills']

export function apply(ctx) {
  return ctx.skills.register({
    name: parsedSkill.name,
    description: parsedSkill.description,
    content: parsedSkill.content,
    invocation: {
      modelInvocable: true,
      userInvocable: true,
    },
    provider: PLUGIN_NAME,
    source: 'bundled',
    resourceBase: {
      kind: 'directory',
      path: fileURLToPath(RESOURCE_DIRECTORY_URL),
    },
  })
}
