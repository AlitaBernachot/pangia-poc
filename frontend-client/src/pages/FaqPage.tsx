// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useState } from 'react'
import { useTranslation, Trans } from 'react-i18next'
import { ChevronDown, ChevronUp, Globe, Database, Zap, Shield, HelpCircle } from 'lucide-react'

const AGENTS_INFO = [
  {
    icon: <Database size={20} className="text-[#4ade80]" />,
    name: 'Neo4j',
    color: 'border-[#4ade80]/30 bg-[rgba(74,222,128,0.06)]',
    descKey: 'faq.agents.neo4j',
  },
  {
    icon: <Globe size={20} className="text-[#fb923c]" />,
    name: 'RDF / SPARQL',
    color: 'border-[#fb923c]/30 bg-[rgba(251,146,60,0.06)]',
    descKey: 'faq.agents.rdf',
  },
  {
    icon: <Zap size={20} className="text-[#60a5fa]" />,
    name: 'Vector / Chroma',
    color: 'border-[#60a5fa]/30 bg-[rgba(96,165,250,0.06)]',
    descKey: 'faq.agents.vector',
  },
  {
    icon: <Globe size={20} className="text-[#38bdf8]" />,
    name: 'PostGIS',
    color: 'border-[#38bdf8]/30 bg-[rgba(56,189,248,0.06)]',
    descKey: 'faq.agents.postgis',
  },
  {
    icon: <Shield size={20} className="text-[#f43f5e]" />,
    name: 'Data.gouv.fr',
    color: 'border-[#f43f5e]/30 bg-[rgba(244,63,94,0.06)]',
    descKey: 'faq.agents.datagouv',
  },
]

const FAQ_KEYS = ['q0', 'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7'] as const

export function FaqPage() {
  const { t } = useTranslation()
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  const toggle = (i: number) => setOpenIndex((prev) => (prev === i ? null : i))

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-12">
      {/* Hero */}
      <section className="text-center space-y-3">
        <div className="inline-flex size-14 rounded-2xl bg-cyan-500/15 border border-cyan-500/25 items-center justify-center">
          <HelpCircle size={26} className="text-cyan-400" />
        </div>
        <h1 className="text-3xl font-semibold text-white">{t('faq.heroTitle')}</h1>
        <p className="text-white/50 text-sm max-w-lg mx-auto">
          {t('faq.heroSubtitle')}
        </p>
      </section>

      {/* About section */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-white">{t('faq.aboutTitle')}</h2>
        <div className="bg-white/3 border border-white/8 rounded-xl px-5 py-4 text-sm text-white/70 leading-relaxed space-y-3">
          <p>{t('faq.aboutP1')}</p>
          <p>
            <Trans
              i18nKey="faq.aboutP2"
              components={{ b: <strong className="text-white/80" /> }}
            />
          </p>
          <p>
            <Trans
              i18nKey="faq.aboutP3"
              components={{
                b: <strong className="text-white/80" />,
                link: (
                  <a
                    href="https://elements.ai-sdk.dev/components/attachments"
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-400 underline"
                  />
                ),
              }}
            />
          </p>
        </div>

        {/* Agent grid */}
        <div className="grid sm:grid-cols-2 gap-3">
          {AGENTS_INFO.map((agent) => (
            <div
              key={agent.name}
              className={`flex items-start gap-3 px-4 py-3 rounded-xl border text-sm ${agent.color}`}
            >
              <span className="mt-0.5 shrink-0">{agent.icon}</span>
              <div>
                <p className="font-medium text-white/90">{agent.name}</p>
                <p className="text-white/50 text-xs">{t(agent.descKey)}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* FAQ accordion */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-white">{t('faq.faqTitle')}</h2>
        <div className="space-y-2">
          {FAQ_KEYS.map((key, i) => {
            const answerKey = key.replace('q', 'a') as `a${number}`
            return (
              <div
                key={key}
                className="border border-white/8 rounded-xl overflow-hidden bg-white/2"
              >
                <button
                  type="button"
                  onClick={() => toggle(i)}
                  className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left text-sm font-medium text-white/80 hover:text-white hover:bg-white/3 transition-colors"
                >
                  <span>{t(`faq.questions.${key}`)}</span>
                  {openIndex === i ? (
                    <ChevronUp size={16} className="text-white/40 shrink-0" />
                  ) : (
                    <ChevronDown size={16} className="text-white/40 shrink-0" />
                  )}
                </button>

                {openIndex === i && (
                  <div className="px-5 pb-4 text-sm text-white/55 leading-relaxed border-t border-white/6 pt-3">
                    {t(`faq.answers.${answerKey}`)}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* Footer note */}
      <p className="text-center text-xs text-white/25 pb-4">
        {t('faq.footerNote')}{' '}
        <a
          href="https://github.com/AlitaBernachot/PangIA-poc"
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-white/50 transition-colors"
        >
          {t('faq.footerGithub')}
        </a>
      </p>
    </div>
  )
}
