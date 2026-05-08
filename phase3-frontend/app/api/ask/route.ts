import { NextRequest, NextResponse } from 'next/server'

export async function POST(req: NextRequest) {
    const body = await req.json()

    const apiUrl = process.env.API_URL

    const response = await fetch(`${apiUrl}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    })

    const data = await response.json()
    console.log("DEBUG: source_url received:", data.source_url)
    return NextResponse.json(data)
}
