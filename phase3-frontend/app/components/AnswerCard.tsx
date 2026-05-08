'use client';

import React from 'react';

interface AnswerCardProps {
    answer: string;
    source_url: string | null;
    last_updated: string | null;
    response_type: "answer" | "refusal" | "pii_block" | "error";
}

const AnswerCard: React.FC<AnswerCardProps> = ({ answer, source_url, last_updated, response_type }) => {
    let cardClass = "p-4 rounded-xl shadow-sm border mb-4 text-sm md:text-base transition-colors ";

    if (response_type === "refusal") {
        cardClass += "bg-amber-50 border-amber-100 text-amber-800";
    } else if (response_type === "pii_block" || response_type === "error") {
        cardClass += "bg-red-50 border-red-100 text-red-800";
    } else {
        cardClass += "bg-gray-50 border-gray-100 text-gray-800";
    }

    const isNoSourceAnswer = answer.toLowerCase().includes("could not find a reliable source");

    function linkifyText(text: string): React.ReactNode[] {
        const urlRegex = /(?:https?:\/\/)?(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z]{2,6}\b(?:[-a-zA-Z0-9@:%_+.~#?&/=]*)/g

        const result: React.ReactNode[] = []
        let lastIndex = 0
        let match

        while ((match = urlRegex.exec(text)) !== null) {
            if (match.index > lastIndex) {
                result.push(text.slice(lastIndex, match.index))
            }
            const url = match[0]
            const href = url.startsWith('http') ? url : `https://${url}`
            result.push(
                <a
                    key={match.index}
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 underline hover:text-blue-800"
                >
                    {url}
                </a>
            )
            lastIndex = match.index + match[0].length
        }

        if (lastIndex < text.length) {
            result.push(text.slice(lastIndex))
        }

        return result
    }

    const renderSources = () => {
        if (!source_url) return null;
        const urls = source_url.split(',');
        return (
            <div className="flex flex-wrap gap-2">
                <span className="text-xs text-gray-500 font-medium">Sources:</span>
                {urls.map((url, index) => (
                    <a
                        key={index}
                        href={url.trim()}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:text-blue-800 hover:underline font-medium inline-flex items-center"
                    >
                        Source {urls.length > 1 ? index + 1 : ''} ↗
                    </a>
                ))}
            </div>
        );
    };

    return (
        <div className={cardClass}>
            <div className="leading-relaxed whitespace-pre-wrap">{linkifyText(answer)}</div>

            {response_type === "answer" && !isNoSourceAnswer && (
                <div className="mt-3 pt-3 border-t border-gray-100 flex flex-col gap-1">
                    {renderSources()}
                    {last_updated && (
                        <span className="text-[10px] text-gray-400">
                            Data last updated: {last_updated}
                        </span>
                    )}
                </div>
            )}

            {response_type === "refusal" && !isNoSourceAnswer && source_url && (
                <div className="mt-2 text-right">
                    <a
                        href={source_url.split(',')[0]} // Show first link for refusal
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-amber-600 hover:text-amber-800 hover:underline font-semibold"
                    >
                        Learn more ↗
                    </a>
                </div>
            )}
        </div>
    );
};

export default AnswerCard;
