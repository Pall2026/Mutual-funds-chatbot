'use client';

import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import ExampleChips from './components/ExampleChips';
import ChatBox from './components/ChatBox';
import AnswerCard from './components/AnswerCard';

interface Message {
    question: string;
    response: {
        answer: string;
        source_url: string | null;
        last_updated: string | null;
        response_type: "answer" | "refusal" | "pii_block" | "error";
    };
}

export default function Home() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleQuestionSubmit = async (question: string) => {
        setIsLoading(true);

        // Optimistically add question to messages
        setMessages(prev => [...prev, {
            question,
            response: {
                answer: "...",
                source_url: null,
                last_updated: null,
                response_type: "answer"
            }
        }]);

        try {
            const res = await fetch('/api/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question })
            });

            const data = await res.json();

            setMessages(prev => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1].response = data;
                return newMessages;
            });
        } catch (error) {
            setMessages(prev => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1].response = {
                    answer: "Sorry, I encountered a connection error. Please try again.",
                    source_url: null,
                    last_updated: null,
                    response_type: "error"
                };
                return newMessages;
            });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <main className="min-h-screen bg-white pb-32">
            <Header />

            <div className="max-w-3xl mx-auto px-4 py-8">
                {/* Welcome Message */}
                <section className="mb-8 border-b pb-6">
                    <p className="text-gray-700 leading-relaxed text-lg">
                        Ask any factual question about SBI Mutual Fund schemes — expense ratios,
                        exit loads, minimum SIP, ELSS lock-in, riskometer, and how to download statements.
                    </p>

                    <ExampleChips onChipClick={handleQuestionSubmit} />

                    <p className="text-xs text-gray-400 italic mt-2 text-center">
                        Facts-only. No investment advice. Always verify with official sources.
                    </p>
                </section>

                {/* Chat History */}
                <div className="space-y-6">
                    {messages.map((msg, idx) => (
                        <div key={idx} className="flex flex-col gap-2">
                            {/* Question bubble */}
                            <div className="self-end bg-[#1B4F8A] text-white p-3 rounded-lg rounded-tr-none max-w-[85%] shadow-sm">
                                <p className="text-sm md:text-base">{msg.question}</p>
                            </div>

                            {/* Answer Card */}
                            <div className="self-start w-full">
                                {msg.response.answer === "..." ? (
                                    <div className="bg-gray-100 p-4 rounded-lg w-16 h-10 flex items-center justify-center animate-pulse">
                                        <div className="flex space-x-1">
                                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full"></div>
                                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full"></div>
                                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full"></div>
                                        </div>
                                    </div>
                                ) : (
                                    <AnswerCard {...msg.response} />
                                )}
                            </div>
                        </div>
                    ))}
                    <div ref={messagesEndRef} />
                </div>
            </div>

            {/* Input Box */}
            <ChatBox onSubmit={handleQuestionSubmit} isLoading={isLoading} />
        </main>
    );
}
