import { NextRequest, NextResponse } from 'next/server'

export async function POST(req: NextRequest) {
    const body = await req.json()

    const apiUrl = process.env.API_URL
    console.log('API_URL:', apiUrl)

    if (!apiUrl) {
        return NextResponse.json({
            answer: 'API URL not configured',
            source_url: null,
            last_updated: null,
            response_type: 'error'
        })
    }

    const response = await fetch(`${apiUrl}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    })

    const data = await response.json()
    console.log("DEBUG: source_url received:", data.source_url)
    return NextResponse.json(data)
}
